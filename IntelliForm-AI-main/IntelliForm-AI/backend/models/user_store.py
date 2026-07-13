"""
User store — MongoDB operations with bcrypt password hashing.
Includes profile CRUD, form history, and key normalization.
"""

import bcrypt
from datetime import datetime
from models import database


# ── Password Hashing ─────────────────────────────────────────────────────────

def hash_password(password):
    """Hash a plain-text password with bcrypt."""
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')


def verify_password(plain_password, hashed_password):
    """Check a plain-text password against a bcrypt hash."""
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


# ── Standard key normalization ───────────────────────────────────────────────

# Maps form labels to canonical profile keys to prevent duplicates
_LABEL_TO_KEY = {
    # Name
    'name': 'name', 'full name': 'name', 'your name': 'name',
    'student name': 'name', 'applicant name': 'name',
    'candidate name': 'name', 'participant name': 'name',
    'name of the student': 'name', 'name of student': 'name',
    'first name': 'first_name', 'last name': 'last_name',
    'middle name': 'middle_name', 'surname': 'last_name',
    # DOB
    'date of birth': 'dob', 'dob': 'dob', 'birthday': 'dob',
    'birth date': 'dob', 'birthdate': 'dob', 'd o b': 'dob',
    # Phone
    'phone': 'phone', 'phone number': 'phone', 'mobile': 'phone',
    'contact number': 'phone', 'mobile number': 'phone',
    'contact no': 'phone', 'phone no': 'phone', 'mobile no': 'phone',
    'whatsapp number': 'phone', 'whatsapp no': 'phone',
    'cell': 'phone', 'cell number': 'phone', 'telephone': 'phone',
    'contact': 'phone',
    # Roll number
    'roll no': 'roll_no', 'roll number': 'roll_no', 'roll no_': 'roll_no',
    'rollno': 'roll_no',
    'registration number': 'roll_no', 'registration no': 'roll_no',
    'enrollment number': 'roll_no', 'enrollment no': 'roll_no',
    'enrolment number': 'roll_no', 'enrolment no': 'roll_no',
    'prn': 'roll_no', 'prn number': 'roll_no', 'prn no': 'roll_no',
    'seat number': 'roll_no', 'seat no': 'roll_no',
    'student id': 'roll_no', 'id number': 'roll_no',
    # Gender
    'gender': 'gender', 'sex': 'gender',
    # Age
    'age': 'age', 'your age': 'age',
    # Email
    'email': 'email', 'email id': 'email', 'email address': 'email',
    'e-mail': 'email', 'mail id': 'email', 'e mail': 'email',
    'your email': 'email',
    # Subject/Course
    'subject': 'subject', 'course': 'subject', 'branch': 'subject',
    'department': 'subject', 'stream': 'subject', 'program': 'subject',
    'programme': 'subject', 'specialization': 'subject',
    # College
    'college': 'college', 'institution': 'college', 'college name': 'college',
    'university': 'college', 'institute': 'college', 'school': 'college',
    'institute name': 'college', 'institution name': 'college',
    'name of college': 'college', 'university name': 'college',
    'school name': 'college',
    # Address
    'address': 'address', 'home address': 'address',
    'residential address': 'address', 'permanent address': 'address',
    'current address': 'address', 'residence': 'address',
    'city': 'city', 'state': 'state',
    'pincode': 'pincode', 'pin code': 'pincode', 'zip code': 'pincode',
    'zip': 'pincode',
    # Education
    'education': 'education', 'qualification': 'education',
    'degree': 'education', 'highest qualification': 'education',
    'education level': 'education',
    # Father / Mother
    'father name': 'father_name', "father's name": 'father_name',
    'fathers name': 'father_name', 'father s name': 'father_name',
    'mother name': 'mother_name', "mother's name": 'mother_name',
    'mothers name': 'mother_name',
    # Year / Division / Semester
    'year': 'year', 'academic year': 'year', 'year of study': 'year',
    'current year': 'year', 'study year': 'year',
    'division': 'division', 'div': 'division',
    'semester': 'semester', 'sem': 'semester', 'current semester': 'semester',
    'section': 'section', 'sec': 'section',
    'class': 'class', 'batch': 'batch',
    'year of passing': 'year_of_passing', 'passing year': 'year_of_passing',
    'graduation year': 'year_of_passing',
    # Blood group
    'blood group': 'blood_group', 'blood type': 'blood_group',
    # Nationality
    'nationality': 'nationality', 'country': 'nationality',
}


def _sanitize_key(key):
    """Sanitize a key for MongoDB (dots and $ are reserved)."""
    clean = key.replace('.', '_').replace('$', '_')
    clean = clean.replace('\n', ' ').replace('*', '').strip()
    return clean


def _normalize_label_to_key(label):
    """Convert a form field label to a canonical profile key."""
    clean = label.replace('*', '').replace('\n', ' ').replace('.', '_').replace('$', '_').strip()
    if not clean:
        return None
    lower = clean.lower().rstrip('.').strip()
    # Try direct lookup
    canonical = _LABEL_TO_KEY.get(lower)
    if canonical:
        return canonical
    # Try with underscores replaced by spaces
    canonical = _LABEL_TO_KEY.get(lower.replace('_', ' '))
    if canonical:
        return canonical
    # Fallback: snake_case the label
    return clean.lower().replace(' ', '_')


# ── User CRUD ─────────────────────────────────────────────────────────────────

def create_user(email, password, name=""):
    """
    Create a new user with a hashed password.
    Returns the user dict on success, None if email already exists.
    """
    try:
        user_doc = {
            "email": email,
            "password": hash_password(password),
            "profile": {
                "name": name,
                "email": email
            },
            "form_history": [],
            "created_at": datetime.utcnow().isoformat(),
        }
        database.users_collection.insert_one(user_doc)
        user_doc.pop('_id', None)
        return user_doc
    except Exception as e:
        if "duplicate key" in str(e).lower() or "E11000" in str(e):
            return None
        raise


def find_user_by_email(email):
    """Find a user by email. Returns dict or None."""
    user = database.users_collection.find_one({"email": email})
    if user:
        user.pop('_id', None)
    return user


def update_user_profile(email, profile_data):
    """
    Update specific fields in a user's profile sub-document.
    Normalizes keys to canonical names to prevent duplicates.
    """
    update_fields = {}
    remove_fields = {}

    for key, value in profile_data.items():
        # Normalize to canonical key
        canonical = _normalize_label_to_key(key) if not key.islower() else _sanitize_key(key)
        if not canonical:
            canonical = _sanitize_key(key)

        if canonical:
            update_fields[f"profile.{canonical}"] = value

            # If the original key was different from canonical, unset the raw key
            # to prevent duplicates in the profile
            raw_sanitized = _sanitize_key(key)
            if raw_sanitized != canonical and raw_sanitized.lower() != canonical:
                remove_fields[f"profile.{raw_sanitized}"] = ""
                # Also try to remove the original mixed-case key
                if key != canonical and key != raw_sanitized:
                    safe_key = key.replace('.', '_').replace('$', '_')
                    remove_fields[f"profile.{safe_key}"] = ""

    if not update_fields:
        return

    update_op = {"$set": update_fields}

    # Remove old duplicate keys if any
    if remove_fields:
        update_op["$unset"] = remove_fields

    database.users_collection.update_one(
        {"email": email},
        update_op
    )


def update_user_password(email, new_password):
    """Update a user's password (hashes it first)."""
    database.users_collection.update_one(
        {"email": email},
        {"$set": {"password": hash_password(new_password)}}
    )


def clean_user_profile(email):
    """
    Clean up a user's profile to remove duplicate/stale keys.
    Re-normalizes all profile keys using the canonical mapping.
    """
    user = find_user_by_email(email)
    if not user or 'profile' not in user:
        return

    raw_profile = user['profile']
    cleaned = {}

    for key, value in raw_profile.items():
        if not value or not str(value).strip():
            continue

        canonical = _normalize_label_to_key(key) if not key.islower() else _sanitize_key(key)
        if not canonical:
            canonical = _sanitize_key(key)

        # Prefer existing canonical data over label-based data
        if canonical in cleaned and key != canonical and not key.islower():
            continue  # Skip label-based duplicates

        cleaned[canonical] = str(value).strip()

    # Replace entire profile with cleaned version
    database.users_collection.update_one(
        {"email": email},
        {"$set": {"profile": cleaned}}
    )

    return cleaned


# ── Form History ──────────────────────────────────────────────────────────────

def _extract_form_id(url):
    """Extract the Google Form ID from a URL."""
    import re
    # Match /d/e/FORM_ID/ or /d/FORM_ID/
    match = re.search(r'/d/(?:e/)?([a-zA-Z0-9_-]+)', url)
    return match.group(1) if match else None


def save_form_history(email, form_url, mapped_data, field_labels, new_profile_fields=None):
    """
    Save a form submission to the user's history.

    Args:
        email:              User's email
        form_url:           The Google Form URL
        mapped_data:        Dict of {entry_id: value}
        field_labels:       Dict of {entry_id: label}
        new_profile_fields: List of field names newly saved to profile
    """
    form_id = _extract_form_id(form_url)
    history_entry = {
        "form_url": form_url,
        "form_id": form_id,
        "mapped_data": mapped_data,
        "field_labels": field_labels,
        "new_profile_fields": new_profile_fields or [],
        "submitted_at": datetime.utcnow().isoformat(),
    }

    database.users_collection.update_one(
        {"email": email},
        {"$push": {"form_history": {"$each": [history_entry], "$position": 0}}}
    )


def get_form_history(email, limit=20):
    """Get the user's form submission history (most recent first)."""
    user = database.users_collection.find_one(
        {"email": email},
        {"form_history": {"$slice": limit}}
    )
    if user:
        return user.get("form_history", [])
    return []


def find_cached_mapping(email, form_url):
    """
    Check if the user has previously filled this exact form.
    Returns the cached mapping or None.
    """
    form_id = _extract_form_id(form_url)
    if not form_id:
        return None

    user = database.users_collection.find_one(
        {"email": email, "form_history.form_id": form_id},
        {"form_history.$": 1}
    )

    if user and user.get("form_history"):
        cached = user["form_history"][0]
        print(f"DEBUG: Found cached mapping for form_id={form_id}")
        return cached

    return None
