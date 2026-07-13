"""
Form field extraction module — requests-based (no Selenium).

Extracts field entry IDs, labels, types, options, and required status
from Google Forms by parsing the FB_PUBLIC_LOAD_DATA_ JavaScript object
embedded in the HTML.

Google Forms type codes:
  0 = Short answer    1 = Paragraph
  2 = Multiple choice (radio)
  3 = Dropdown        4 = Checkboxes
  5 = Linear scale    7 = Grid (multiple choice)
  9 = Date           10 = Time
"""

import re
import json
import requests


# ── Google Forms type code -> human-readable type ────────────────────────────

GFORM_TYPE_MAP = {
    0: "text",
    1: "paragraph",
    2: "radio",
    3: "dropdown",
    4: "checkbox",
    5: "linear_scale",
    7: "grid",
    9: "date",
    10: "time",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_short_url(url):
    """Resolve forms.gle short URLs to the full docs.google.com URL."""
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


def _extract_fb_public_load_data(html):
    """
    Extract the FB_PUBLIC_LOAD_DATA_ JavaScript variable from Google Forms HTML.

    The variable is embedded as:
        var FB_PUBLIC_LOAD_DATA_ = [ ... ];

    Returns the parsed Python list, or None on failure.
    """
    # Pattern: var FB_PUBLIC_LOAD_DATA_ = <JSON array>;
    pattern = r'var\s+FB_PUBLIC_LOAD_DATA_\s*=\s*(\[.*?\])\s*;'
    match = re.search(pattern, html, re.DOTALL)

    if not match:
        print("DEBUG: FB_PUBLIC_LOAD_DATA_ not found in HTML")
        return None

    raw_json = match.group(1)

    try:
        data = json.loads(raw_json)
        print(f"DEBUG: Successfully parsed FB_PUBLIC_LOAD_DATA_ (top-level items: {len(data)})")
        return data
    except json.JSONDecodeError as e:
        print(f"DEBUG: JSON parse error: {e}")
        # Try cleaning common issues
        try:
            # Sometimes there are trailing commas or other issues
            cleaned = re.sub(r',\s*]', ']', raw_json)
            cleaned = re.sub(r',\s*}', '}', cleaned)
            data = json.loads(cleaned)
            print(f"DEBUG: Parsed after cleanup (top-level items: {len(data)})")
            return data
        except json.JSONDecodeError:
            print("DEBUG: Could not parse even after cleanup")
            return None


def _parse_form_fields_from_data(data):
    """
    Parse the FB_PUBLIC_LOAD_DATA_ structure to extract all form fields.

    The structure (simplified):
        data[1][1]  = list of field groups (question items)

    Each field item at data[1][1][i]:
        [0] = question ID (internal)
        [1] = label / title text
        [2] = description (can be null)
        [3] = ??? (usually 0 or 2)
        [4] = list of sub-fields, each sub-field:
              [0] = entry ID (numeric)
              [1] = list of options: [[opt_text, null, ...], ...] or null
              [2] = required flag (1 = required, 0 = optional)
              [3] = ??? 
              ... varies by type
        [5] = ??? 
        ... (other metadata)

    The type code appears to be at item[3] in the field item structure.
    """
    fields = []

    try:
        # data[1][1] contains the list of form items (questions)
        form_items = data[1][1]
        if not form_items:
            print("DEBUG: No form items found at data[1][1]")
            return fields

        print(f"DEBUG: Found {len(form_items)} form items")

        for idx, item in enumerate(form_items):
            try:
                if not item or not isinstance(item, list):
                    continue

                # Label / title
                label = item[1] if len(item) > 1 and isinstance(item[1], str) else None
                if not label:
                    label = f"Question {idx + 1}"

                # Clean label
                label = label.replace('*', '').replace('\n', ' ').strip()

                # Get the sub-fields array (index 4)
                sub_fields = item[4] if len(item) > 4 and isinstance(item[4], list) else None
                if not sub_fields:
                    print(f"  DEBUG: Item '{label}' has no sub-fields, skipping")
                    continue

                # Get the type code from the PARENT item (index 3), not sub-field
                type_code = item[3] if len(item) > 3 and isinstance(item[3], int) else 0
                field_type = GFORM_TYPE_MAP.get(type_code, "text")

                for sub in sub_fields:
                    if not sub or not isinstance(sub, list):
                        continue

                    # Entry ID (index 0)
                    entry_id = sub[0] if len(sub) > 0 else None
                    if entry_id is None:
                        continue

                    entry_name = f"entry.{entry_id}"

                    # Options (index 1) -- for radio, dropdown, checkbox, linear_scale
                    options = []
                    if type_code in (2, 3, 4, 5):
                        raw_options = sub[1] if len(sub) > 1 and isinstance(sub[1], list) else []
                        for opt in raw_options:
                            if opt and isinstance(opt, list) and len(opt) > 0 and opt[0]:
                                opt_text = str(opt[0]).strip()
                                if opt_text:  # Skip empty "Other" options
                                    options.append(opt_text)

                    # Required flag (index 2)
                    required = bool(sub[2]) if len(sub) > 2 else False

                    print(f"  DEBUG: Field '{label}' -> entry.{entry_id}, type={field_type}, "
                          f"options={options}, required={required}")

                    fields.append({
                        "name": entry_name,
                        "label": label,
                        "type": field_type,
                        "options": options,
                        "required": required,
                    })

            except (IndexError, TypeError) as e:
                print(f"  DEBUG: Error parsing item {idx}: {e}")
                continue

    except (IndexError, TypeError, KeyError) as e:
        print(f"DEBUG: Error navigating FB_PUBLIC_LOAD_DATA_ structure: {e}")

    return fields


# ── Main Google Forms extractor ─────────────────────────────────────────────

def extract_google_form_fields(url):
    """
    Extract fields from a Google Form using requests + FB_PUBLIC_LOAD_DATA_.

    No Selenium, no Chrome — pure HTTP + JSON parsing.

    Returns list of dicts:
      [{"name": "entry.123", "label": "Your Name", "type": "text",
        "options": [], "required": True}, ...]
    """
    fields = []

    try:
        # Step 1: Resolve short URLs
        full_url = _resolve_short_url(url)

        # Step 2: Fetch the form HTML
        headers = {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
            'Accept-Language': 'en-US,en;q=0.9',
        }

        print(f"DEBUG: Fetching form URL: {full_url}")
        resp = requests.get(full_url, headers=headers, timeout=15)
        resp.raise_for_status()

        html = resp.text
        print(f"DEBUG: Got HTML response, length: {len(html)}")

        # Step 3: Extract FB_PUBLIC_LOAD_DATA_
        data = _extract_fb_public_load_data(html)

        if data:
            # Step 4: Parse fields from the data structure
            fields = _parse_form_fields_from_data(data)
            print(f"DEBUG: Extracted {len(fields)} fields via FB_PUBLIC_LOAD_DATA_")

        # Step 5: Fallback — regex for entry IDs if FB_PUBLIC_LOAD_DATA_ failed
        if not fields:
            print("DEBUG: FB_PUBLIC_LOAD_DATA_ extraction found 0 fields, trying regex fallback...")
            entry_ids = re.findall(r'entry\.(\d{7,10})', html)
            entry_ids = list(dict.fromkeys(entry_ids))  # deduplicate, preserve order
            print(f"DEBUG: Regex found entry IDs: {entry_ids}")

            # Try to extract labels from HTML
            label_pattern = r'data-item-id="[^"]*"[^>]*>.*?<span[^>]*>(.*?)</span>'
            raw_labels = re.findall(label_pattern, html, re.DOTALL)
            labels = [l.strip() for l in raw_labels if l.strip() and len(l.strip()) < 200]

            for i, eid in enumerate(entry_ids):
                label = labels[i] if i < len(labels) else f"Field {i + 1}"
                label = label.replace('*', '').replace('\n', ' ').strip()
                fields.append({
                    "name": f"entry.{eid}",
                    "label": label,
                    "type": "text",
                    "options": [],
                    "required": False,
                })

        print(f"DEBUG: FINAL extracted fields: {json.dumps(fields, indent=2, ensure_ascii=False)}")

    except requests.RequestException as e:
        print(f"Google Form fetch error: {e}")
    except Exception as e:
        print(f"Google Form extraction error: {e}")
        import traceback
        traceback.print_exc()

    return fields


# ── Generic HTML form extractor (kept for non-Google forms) ─────────────────

def extract_generic_form_fields(url):
    """
    For non-Google forms — extract fields from standard HTML forms using requests.
    """
    fields = []
    seen = set()

    try:
        headers = {
            'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                           'AppleWebKit/537.36 (KHTML, like Gecko) '
                           'Chrome/120.0.0.0 Safari/537.36'),
        }
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Extract input fields
        input_pattern = r'<input[^>]*>'
        for match in re.finditer(input_pattern, html, re.IGNORECASE):
            tag = match.group()

            name_match = re.search(r'name=["\']([^"\']+)["\']', tag)
            if not name_match:
                continue
            name = name_match.group(1)
            if name in seen:
                continue
            seen.add(name)

            type_match = re.search(r'type=["\']([^"\']+)["\']', tag)
            input_type = type_match.group(1) if type_match else 'text'

            if input_type in ('hidden', 'submit', 'button', 'reset', 'image'):
                continue

            # Try to find a label
            label = ''
            placeholder_match = re.search(r'placeholder=["\']([^"\']+)["\']', tag)
            if placeholder_match:
                label = placeholder_match.group(1)

            if not label:
                aria_match = re.search(r'aria-label=["\']([^"\']+)["\']', tag)
                if aria_match:
                    label = aria_match.group(1)

            fields.append({
                'name': name,
                'label': label or name,
                'type': input_type,
                'options': [],
                'required': 'required' in tag.lower(),
            })

    except Exception as e:
        print(f"Generic form extraction error: {e}")

    return fields


# ── Router ───────────────────────────────────────────────────────────────────

def extract_form_fields(url):
    """Route to the right extractor based on URL."""
    if 'docs.google.com/forms' in url or 'forms.gle' in url:
        return extract_google_form_fields(url)
    return extract_generic_form_fields(url)