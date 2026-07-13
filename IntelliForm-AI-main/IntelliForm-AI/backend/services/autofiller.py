"""
Google Form Autofill via Pre-Fill URL.

Constructs Google Forms pre-fill URLs with proper handling for all field types:
  - Text/Paragraph:  entry.XXX=value
  - Radio/Dropdown:  entry.XXX=Exact Option Text
  - Checkbox:        entry.XXX=Option1&entry.XXX=Option2 (repeated param)
  - Date:            entry.XXX_year=YYYY&entry.XXX_month=M&entry.XXX_day=D
  - Time:            entry.XXX_hour=HH&entry.XXX_minute=MM
"""

import re
import requests
from datetime import datetime
from urllib.parse import urlencode, quote


def _resolve_short_url(url):
    """
    Resolve forms.gle short URLs to full docs.google.com URLs.
    Example: https://forms.gle/abc123 → https://docs.google.com/forms/d/e/XXX/viewform
    """
    if 'forms.gle' not in url:
        return url

    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        resolved = resp.url
        print(f"  Resolved short URL: {url} -> {resolved}")
        return resolved
    except Exception as e:
        print(f"  [WARN] Could not resolve short URL: {e}")
        return url


def _normalize_viewform_url(url):
    """
    Ensure the URL ends with /viewform (strip query params and fragments).
    """
    base = url.split('?')[0].split('#')[0]
    base = base.replace('/formResponse', '/viewform')
    if not base.endswith('/viewform'):
        base = base.rstrip('/') + '/viewform'
    return base


def _parse_date(value):
    """
    Parse a date value (YYYY-MM-DD or other formats) into (year, month, day) strings.
    Google Forms date pre-fill uses: entry.XXX_year=YYYY&entry.XXX_month=M&entry.XXX_day=D
    Note: month and day should NOT have leading zeros for Google Forms.
    """
    value = str(value).strip()
    formats = [
        '%Y-%m-%d',    # 2003-08-15
        '%d-%m-%Y',    # 15-08-2003
        '%m-%d-%Y',    # 08-15-2003
        '%d/%m/%Y',    # 15/08/2003
        '%m/%d/%Y',    # 08/15/2003
        '%Y/%m/%d',    # 2003/08/15
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(value, fmt)
            return str(dt.year), str(dt.month), str(dt.day)
        except ValueError:
            continue

    # Last resort: extract numbers
    nums = re.findall(r'\d+', value)
    if len(nums) >= 3:
        a, b, c = int(nums[0]), int(nums[1]), int(nums[2])
        if a > 31:   # YYYY-MM-DD
            return str(a), str(b), str(c)
        elif c > 31: # DD-MM-YYYY
            return str(c), str(b), str(a)
        else:        # Assume DD-MM-YYYY
            return str(c), str(b), str(a)

    return None, None, None


def _parse_time(value):
    """
    Parse a time value (HH:MM) into (hour, minute) strings.
    Google Forms time pre-fill uses: entry.XXX_hour=HH&entry.XXX_minute=MM
    """
    value = str(value).strip()
    match = re.match(r'(\d{1,2}):(\d{2})', value)
    if match:
        return match.group(1), match.group(2)

    nums = re.findall(r'\d+', value)
    if len(nums) >= 2:
        return str(int(nums[0])), str(int(nums[1]))

    return None, None


def build_prefill_url(form_url, mapped_data, form_fields=None):
    """
    Build a Google Forms pre-fill URL from mapped entry data.

    Args:
        form_url:     The Google Form URL (can be short or full)
        mapped_data:  Dict of {"entry.XXXXX": "value", ...}
                      Checkbox values should be lists: {"entry.XXXXX": ["Opt1", "Opt2"]}
        form_fields:  List of field dicts from form_extractor (for type info)
                      [{"name": "entry.123", "type": "date", "options": []}, ...]

    Returns:
        A fully-formed pre-fill URL string, or None on failure.
    """
    try:
        # Step 1: Resolve short URLs
        full_url = _resolve_short_url(form_url)

        # Step 2: Normalize to /viewform
        base_url = _normalize_viewform_url(full_url)

        # Step 3: Build field type lookup from metadata
        type_lookup = {}
        if form_fields:
            for f in form_fields:
                type_lookup[f['name']] = f.get('type', 'text')

        # Step 4: Build query params — use list of tuples (supports repeated keys for checkboxes)
        params = []

        for key, value in mapped_data.items():
            if value is None:
                continue

            field_type = type_lookup.get(key, 'text')
            entry_num = key.replace('entry.', '')

            # ── Date: split into year/month/day ──────────────────────────
            if field_type == 'date':
                year, month, day = _parse_date(value)
                if year and month and day:
                    params.append((f'entry.{entry_num}_year', year))
                    params.append((f'entry.{entry_num}_month', month))
                    params.append((f'entry.{entry_num}_day', day))
                    print(f"  [DATE] Date '{key}': {value} -> {year}-{month}-{day}")
                else:
                    print(f"  [WARN] Could not parse date for '{key}': {value}")
                continue

            # ── Time: split into hour/minute ─────────────────────────────
            if field_type == 'time':
                hour, minute = _parse_time(value)
                if hour and minute:
                    params.append((f'entry.{entry_num}_hour', hour))
                    params.append((f'entry.{entry_num}_minute', minute))
                    print(f"  [TIME] Time '{key}': {value} -> {hour}:{minute}")
                else:
                    print(f"  [WARN] Could not parse time for '{key}': {value}")
                continue

            # ── Checkbox: repeat same key for each selected option ────────
            if field_type == 'checkbox':
                if isinstance(value, list):
                    for v in value:
                        if v and str(v).strip():
                            params.append((key, str(v).strip()))
                    print(f"  [CHECK] Checkbox '{key}': {value}")
                elif str(value).strip():
                    params.append((key, str(value).strip()))
                continue

            # ── Radio / Dropdown / Text / Paragraph / Linear Scale ───────
            str_value = str(value).strip()
            if str_value:
                params.append((key, str_value))
                if field_type in ('radio', 'dropdown'):
                    print(f"  [RADIO] {field_type.title()} '{key}': {str_value}")

        if not params:
            print("  [WARN] No data to pre-fill")
            return None

        # Step 5: Construct the URL
        prefill_url = f"{base_url}?{urlencode(params, quote_via=quote)}"

        print(f"\n{'='*60}")
        print(f"[OK] Pre-fill URL built successfully!")
        print(f"   Base: {base_url}")
        print(f"   Fields: {len(params)} params")
        print(f"   URL length: {len(prefill_url)} chars")
        print(f"{'='*60}\n")

        return prefill_url

    except Exception as e:
        print(f"[ERROR] Error building pre-fill URL: {e}")
        import traceback
        traceback.print_exc()
        return None


# Keep backward compatibility
def autofill_form(url, mapped_data, form_fields=None):
    """Legacy wrapper."""
    return build_prefill_url(url, mapped_data, form_fields)