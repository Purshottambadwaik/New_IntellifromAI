"""
AI-powered field mapping using Gemini.

Maps form fields to user profile data using semantic understanding.
Returns confidence scores for each match (high / medium / low).

Handles different field types:
  - text/paragraph  → profile value as-is
  - radio/dropdown  → picks exact option from available choices
  - checkbox        → returns list of selected options
  - date            → returns YYYY-MM-DD format
  - time            → returns HH:MM format
  - linear_scale    → picks numeric value from range
"""

import os
import json
import re
from datetime import datetime
from google import genai

import config

# Load Gemini API key from config
GEMINI_API_KEY = config.GEMINI_API_KEY if hasattr(config, 'GEMINI_API_KEY') else os.environ.get('GEMINI_API_KEY', '')
client = genai.Client(api_key=GEMINI_API_KEY)


# ── Standard profile key aliases ────────────────────────────────────────────
# Maps form labels (saved to profile) back to canonical keys

_KEY_ALIASES = {
    # Name
    'full name': 'name', 'your name': 'name', 'student name': 'name',
    'applicant name': 'name', 'candidate name': 'name', 'participant name': 'name',
    'name of the student': 'name', 'name of student': 'name',
    'name of the candidate': 'name', 'name of the applicant': 'name',
    'first name': 'first_name', 'last name': 'last_name', 'surname': 'last_name',
    'middle name': 'middle_name',
    # DOB
    'date of birth': 'dob', 'birthday': 'dob', 'birth date': 'dob',
    'd_o_b': 'dob', 'date_of_birth': 'dob', 'd.o.b': 'dob', 'd o b': 'dob',
    'dob': 'dob', 'birthdate': 'dob',
    # Phone
    'phone number': 'phone', 'mobile': 'phone', 'mobile number': 'phone',
    'contact number': 'phone', 'cell': 'phone', 'whatsapp number': 'phone',
    'whatsapp no': 'phone', 'contact no': 'phone', 'phone no': 'phone',
    'mobile no': 'phone', 'cell number': 'phone', 'telephone': 'phone',
    'contact': 'phone',
    # Roll number
    'roll number': 'roll_no', 'roll no': 'roll_no', 'rollno': 'roll_no',
    'registration number': 'roll_no', 'registration no': 'roll_no',
    'enrollment number': 'roll_no', 'enrollment no': 'roll_no',
    'enrolment number': 'roll_no', 'enrolment no': 'roll_no',
    'prn': 'roll_no', 'prn number': 'roll_no', 'prn no': 'roll_no',
    'seat number': 'roll_no', 'seat no': 'roll_no',
    'student id': 'roll_no', 'id number': 'roll_no',
    # Email
    'email id': 'email', 'email address': 'email', 'e-mail': 'email',
    'mail id': 'email', 'e mail': 'email', 'your email': 'email',
    'email': 'email',
    # Gender
    'sex': 'gender', 'gender': 'gender',
    # Age
    'age': 'age', 'your age': 'age',
    # Subject/Course
    'course': 'subject', 'program': 'subject', 'branch': 'subject',
    'department': 'subject', 'stream': 'subject', 'subject': 'subject',
    'programme': 'subject', 'specialization': 'subject',
    # College
    'college name': 'college', 'institution': 'college',
    'university': 'college', 'college_university': 'college',
    'school': 'college', 'institute': 'college', 'college': 'college',
    'institute name': 'college', 'institution name': 'college',
    'name of college': 'college', 'name of institution': 'college',
    'school name': 'college', 'university name': 'college',
    # Father
    'father name': 'father_name', "father's name": 'father_name',
    'fathers name': 'father_name', 'father s name': 'father_name',
    "mother's name": 'mother_name', 'mother name': 'mother_name',
    'mothers name': 'mother_name',
    # Address
    'home address': 'address', 'residential address': 'address',
    'permanent address': 'address', 'current address': 'address',
    'address': 'address', 'residence': 'address',
    'city': 'city', 'state': 'state', 'pincode': 'pincode',
    'pin code': 'pincode', 'zip code': 'pincode', 'zip': 'pincode',
    # Education
    'qualification': 'education', 'degree': 'education',
    'highest qualification': 'education', 'education': 'education',
    'education level': 'education',
    # Year / Division / Semester / Section
    'year': 'year', 'academic year': 'year', 'year of study': 'year',
    'current year': 'year', 'study year': 'year',
    'division': 'division', 'div': 'division',
    'semester': 'semester', 'sem': 'semester', 'current semester': 'semester',
    'section': 'section', 'sec': 'section',
    'class': 'class', 'batch': 'batch', 'year of passing': 'year_of_passing',
    'passing year': 'year_of_passing', 'graduation year': 'year_of_passing',
    # Blood group
    'blood group': 'blood_group', 'blood type': 'blood_group',
    # Nationality
    'nationality': 'nationality', 'country': 'nationality',
}


def _normalize_profile(raw_profile):
    """
    Normalize profile keys to eliminate duplicates.

    Problem: When users fill 'missing fields', raw form labels (e.g., 'Name',
    'Date of birth') get saved as profile keys, creating DUPLICATES:
      profile = {"name": "John", "Name": "John Doe", "dob": "2000-11-30", "Date of birth": "30-02-2000"}

    This function merges them, PREFERRING the original clean profile data
    (lowercase keys like 'name', 'dob') over form-label-based duplicates.
    """
    original_data = {}
    label_data = {}

    for key, value in raw_profile.items():
        if not value or not str(value).strip():
            continue

        # Clean the key
        clean = key.replace('\n', ' ').replace('*', '').replace('$', '_').strip()
        if not clean:
            continue

        str_val = str(value).strip()

        # Normalize to canonical key
        lower = clean.lower().replace('.', ' ').replace('_', ' ').strip()
        # Also try with underscores for keys like "roll_no"
        lower_underscore = clean.lower().replace('.', '_').replace(' ', '_').strip()
        canonical_key = _KEY_ALIASES.get(lower) or _KEY_ALIASES.get(lower_underscore)

        if canonical_key:
            # Known alias — only use if we don't already have the canonical
            if canonical_key not in original_data:
                label_data[canonical_key] = str_val
        elif key.islower() or key.replace('_', '').islower() or key == 'email':
            # Original profile keys are always lowercase (or snake_case)
            safe_key = clean.replace('.', '_').replace(' ', '_').lower()
            original_data[safe_key] = str_val
        else:
            # Not lowercase = probably saved from a form label — low priority
            lower_clean = clean.lower().replace(' ', '_').replace('.', '_')
            if lower_clean not in original_data:
                label_data[lower_clean] = str_val

    # Merge: originals overwrite label-based data
    merged = {}
    merged.update(label_data)
    merged.update(original_data)

    return merged


def smart_map_fields(fields, user):
    """
    Use Gemini to intelligently map form fields to user profile data.

    Args:
        fields: List of field dicts from form_extractor
                [{"name": "entry.123", "label": "Full Name", "type": "text", "options": []}, ...]
        user:   User document from MongoDB (has 'email' and 'profile' dict)

    Returns:
        (mapped_data, missing_fields, confidence_scores)
        mapped_data:       {"entry.123": "John", "entry.456": "Male"}
        missing_fields:    [field_dicts that couldn't be mapped]
        confidence_scores: {"entry.123": "high", "entry.456": "medium"}
    """
    # ── Build and NORMALIZE profile ──────────────────────────────────────
    raw_profile = dict(user.get("profile", {}))
    if 'email' not in raw_profile and user.get('email'):
        raw_profile['email'] = user['email']

    clean_profile = _normalize_profile(raw_profile)

    profile_summary = json.dumps(clean_profile, indent=2, ensure_ascii=False)
    print(f"DEBUG normalized profile: {profile_summary}")

    # ── Build enhanced fields description ────────────────────────────────
    fields_for_prompt = []
    for f in fields:
        field_desc = {
            "name": f["name"],
            "label": f["label"],
            "type": f.get("type", "text"),
        }
        if f.get("options"):
            field_desc["options"] = f["options"]
        fields_for_prompt.append(field_desc)

    fields_summary = json.dumps(fields_for_prompt, indent=2, ensure_ascii=False)

    # ── Build Gemini prompt ──────────────────────────────────────────────
    prompt = f"""You are an expert form-filling assistant. Your job is to SEMANTICALLY match form field labels to user profile data, even when the names differ.

## User Profile Data (key → value):
{profile_summary}

## Form Fields (with types and available options):
{fields_summary}

## CRITICAL RULES:

### Semantic Matching (MOST IMPORTANT):
- Match labels by MEANING, not exact text. Examples:
  - "Your full name", "Full Name", "Name", "Applicant Name", "Student Name" → all match the user's name
  - "Date of birth", "DOB", "Birthday", "Birth Date" → all match dob
  - "Phone number", "Mobile", "Contact Number", "Cell" → all match phone
  - "Roll no", "Roll Number", "Registration No", "Enrollment No", "PRN" → all match roll number
  - "Email ID", "E-mail", "Email Address" → all match email
  - "Gender", "Sex" → match gender
  - "Age" → match age
  - "College", "Institution", "University" → match college/university
  - "Course", "Program", "Subject", "Branch", "Department" → match course/subject
  - "Father's Name", "Father Name" → match father/father's name
  - "Mother's Name", "Mother Name" → match mother/mother's name
  - "Address", "Residence" → match address
  - "Year", "Year of Study", "Academic Year" → match year
  - "Division", "Div" → match division
  - "Semester", "Sem" → match semester
  - "Section", "Sec" → match section
  - "Blood Group", "Blood Type" → match blood_group

### Type-Specific Rules:
1. **"radio" or "dropdown"**: MUST pick EXACTLY one value from the "options" list.
   - Match closest option semantically. E.g., profile gender="male", options=["Male","Female","Other"] → "Male"
   - NEVER return a value NOT in the options list.

2. **"checkbox"**: Return a JSON array of selected options from the "options" list.
   - Only include options that match.

3. **"date"**: Return in YYYY-MM-DD format.

4. **"time"**: Return in HH:MM format (24-hour).

5. **"linear_scale"**: Pick a number from the options.

6. **"text" or "paragraph"**: Return the profile value as-is.

### Confidence Scoring:
For EACH field, also provide a confidence level:
- "high"   — exact or near-exact semantic match (e.g., "Name" → profile.name)
- "medium" — reasonable inference (e.g., "Your good name" → profile.name)
- "low"    — uncertain/weak match
- null     — no match at all (value should also be null)

### Output Format:
Respond ONLY with a raw JSON object. No markdown, no explanation, no code fences.
Each key is the field name (entry.XXXX), value is an object with "value" and "confidence":

{{"entry.123": {{"value": "John Doe", "confidence": "high"}}, "entry.456": {{"value": "Male", "confidence": "high"}}, "entry.789": {{"value": null, "confidence": null}}}}"""

    # ── Call Gemini (with retry for rate limits) ─────────────────────────
    import time as _time
    max_retries = 3
    last_error = None

    for attempt in range(1, max_retries + 1):
        try:
            print(f"DEBUG: Gemini attempt {attempt}/{max_retries}")
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            text = response.text.strip()
            print(f"DEBUG Gemini raw response:\n{text}")

            # Clean response -- remove markdown code fences if present
            if "```" in text:
                parts = text.split("```")
                if len(parts) >= 3:
                    text = parts[1]
                else:
                    text = parts[-1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()

            raw_mapped = json.loads(text)

            # ── Extract values and confidence scores ────────────────────
            mapped = {}
            confidence_scores = {}

            for field in fields:
                fname = field["name"]
                entry = raw_mapped.get(fname, {})

                # Handle both new format {value, confidence} and legacy format
                if isinstance(entry, dict) and "value" in entry:
                    val = entry.get("value")
                    conf = entry.get("confidence")
                else:
                    val = entry
                    conf = "medium" if val else None

                if val is None or val == "":
                    confidence_scores[fname] = None
                    continue

                confidence_scores[fname] = conf

                # Post-process by type
                if field.get("type") == "checkbox":
                    if isinstance(val, str):
                        mapped[fname] = [val]
                    elif isinstance(val, list):
                        mapped[fname] = val
                    else:
                        mapped[fname] = [str(val)]
                elif field.get("type") in ("radio", "dropdown"):
                    if isinstance(val, list):
                        val = val[0] if val else None
                    if field.get("options") and val and val not in field["options"]:
                        for opt in field["options"]:
                            if opt.lower() == str(val).lower():
                                val = opt
                                break
                    mapped[fname] = val
                elif field.get("type") == "date":
                    mapped[fname] = _normalize_date(str(val))
                else:
                    mapped[fname] = str(val).strip() if val else None

            missing = [f for f in fields if not mapped.get(f["name"])]
            final_mapped = {k: v for k, v in mapped.items() if v is not None and v != ""}

            print(f"\nDEBUG final mapped: {json.dumps(final_mapped, indent=2, ensure_ascii=False)}")
            print(f"DEBUG confidence: {json.dumps(confidence_scores, indent=2)}")
            print(f"DEBUG missing: {[f['label'] for f in missing]}")

            return final_mapped, missing, confidence_scores

        except Exception as e:
            last_error = e
            error_str = str(e).lower()
            # Retry on rate limit (429) or quota errors
            if '429' in error_str or 'rate' in error_str or 'quota' in error_str or 'resource' in error_str:
                wait = 2 ** attempt  # 2s, 4s, 8s
                print(f"[WARN] Gemini rate-limited (attempt {attempt}/{max_retries}). Waiting {wait}s...")
                _time.sleep(wait)
                continue
            else:
                print(f"Gemini mapping error (non-retryable): {e}")
                import traceback
                traceback.print_exc()
                break

    # ── FALLBACK: local matching when Gemini is unavailable ─────────────
    print(f"[WARN] Gemini failed after {max_retries} attempts: {last_error}")
    print("[INFO] Using local profile-matching fallback...")
    return _local_fallback_match(fields, clean_profile)


def _normalize_date(date_str):
    """
    Normalize a date string to YYYY-MM-DD format.
    """
    date_str = date_str.strip()
    formats = [
        '%Y-%m-%d', '%d-%m-%Y', '%m-%d-%Y',
        '%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d',
        '%d %b %Y', '%d %B %Y', '%b %d, %Y', '%B %d, %Y',
        '%d-%b-%Y', '%d-%B-%Y',
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue

    # Last resort: extract numbers
    nums = re.findall(r'\d+', date_str)
    if len(nums) >= 3:
        a, b, c = int(nums[0]), int(nums[1]), int(nums[2])
        if a > 31:
            return f"{a:04d}-{b:02d}-{c:02d}"
        elif c > 31:
            return f"{c:04d}-{b:02d}-{a:02d}"

    return date_str


def _local_fallback_match(fields, profile):
    """
    Local fallback when Gemini is unavailable (rate-limited, no API key, etc).
    Uses _KEY_ALIASES to match form labels to profile keys.
    """
    mapped = {}
    confidence_scores = {}

    print("[FALLBACK] Profile keys available:", list(profile.keys()))

    for field in fields:
        fname = field["name"]
        label = field.get("label", "").strip()
        ftype = field.get("type", "text")
        options = field.get("options", [])

        # Normalize label for lookup
        label_lower = label.lower().replace('.', ' ').replace('_', ' ').replace(':', '').strip()
        label_underscore = label.lower().replace('.', '_').replace(' ', '_').replace(':', '').strip()

        # Look up canonical key via aliases
        canonical = _KEY_ALIASES.get(label_lower) or _KEY_ALIASES.get(label_underscore)

        # Also try the raw label as a direct profile key
        if not canonical:
            if label_lower in profile:
                canonical = label_lower
            elif label_underscore in profile:
                canonical = label_underscore

        # Try to find profile value
        val = None
        if canonical and canonical in profile:
            val = profile[canonical]
            print(f"  [MATCH] '{label}' -> profile['{canonical}'] = '{val}'")

        if val is None or str(val).strip() == "":
            confidence_scores[fname] = None
            print(f"  [MISS]  '{label}' -> no match in profile")
            continue

        confidence_scores[fname] = "high"

        # Post-process by type
        if ftype == "checkbox":
            if options:
                matched_opts = []
                for opt in options:
                    if opt.lower() == str(val).lower():
                        matched_opts.append(opt)
                mapped[fname] = matched_opts if matched_opts else [str(val)]
            else:
                mapped[fname] = [str(val)]

        elif ftype in ("radio", "dropdown"):
            if options:
                matched_opt = None
                for opt in options:
                    if opt.lower() == str(val).lower():
                        matched_opt = opt
                        break
                mapped[fname] = matched_opt or str(val)
            else:
                mapped[fname] = str(val)

        elif ftype == "date":
            mapped[fname] = _normalize_date(str(val))

        else:
            mapped[fname] = str(val).strip()

    missing = [f for f in fields if not mapped.get(f["name"])]
    final_mapped = {k: v for k, v in mapped.items() if v is not None and v != ""}

    print(f"\n[FALLBACK] Matched {len(final_mapped)} fields, {len(missing)} missing")
    return final_mapped, missing, confidence_scores