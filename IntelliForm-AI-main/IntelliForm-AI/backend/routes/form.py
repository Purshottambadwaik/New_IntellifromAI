from flask import Blueprint, render_template, request, redirect, flash, session, g, jsonify
from models.user_store import (
    find_user_by_email, update_user_profile,
    save_form_history, get_form_history, find_cached_mapping,
)
from services.form_extractor import extract_form_fields
from services.ai_mapper import smart_map_fields
from services.autofiller import build_prefill_url
from utils.auth import login_required

form_bp = Blueprint('form', __name__)


# ── Hardcoded profile keys (used to detect "custom" fields) ──────────────────

_STANDARD_PROFILE_KEYS = {
    'name', 'email', 'phone', 'dob', 'age', 'gender', 'address',
    'father_name', 'mother_name', 'education', 'college', 'roll_no',
    'subject', 'city', 'state', 'pincode', 'nationality',
    'first_name', 'last_name', 'middle_name',
}


# ── PROFILE ──────────────────────────────────────────────────────────────────

@form_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = find_user_by_email(g.current_user_email)

    if request.method == 'POST':
        profile_data = {}
        for key, value in request.form.items():
            if value.strip():
                profile_data[key] = value.strip()
        update_user_profile(g.current_user_email, profile_data)
        flash("Profile saved successfully!", "success")
        return redirect('/dashboard')

    user_profile = user.get('profile', {})

    # Split profile into standard and custom fields
    custom_fields = {}
    for key, value in user_profile.items():
        if key not in _STANDARD_PROFILE_KEYS and value and str(value).strip():
            custom_fields[key] = value

    return render_template('profile.html', profile=user_profile, custom_fields=custom_fields)


# ── DASHBOARD ────────────────────────────────────────────────────────────────

@form_bp.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    user = find_user_by_email(g.current_user_email)

    if request.method == 'POST' and 'form_url' in request.form:
        url = request.form['form_url'].strip()
        import logging
        log = logging.getLogger('form.dashboard')
        log.info(f"POST /dashboard with url={url[:80]}...")

        if not url:
            flash("Please enter a Google Form URL.", "error")
            return redirect('/dashboard')

        try:
            session['form_url'] = url

            # -- Always do fresh extraction when URL is submitted from dashboard --
            log.info("Step 1: Extracting form fields...")
            fields = extract_form_fields(url)
            log.info(f"Step 1 result: {len(fields)} fields extracted")

            if not fields:
                log.warning("No fields extracted!")
                flash("No fields found. Make sure the URL is a valid public Google Form.", "error")
                session.pop('mapped_data', None)
                session.pop('missing_fields', None)
                session.pop('form_fields', None)
                session.pop('confidence_scores', None)
                return redirect('/dashboard')

            # Store field metadata
            session['form_fields'] = fields

            for f in fields:
                log.info(f"  Field: {f['name']} | {f['label']} | type={f.get('type','?')}")

            # -- AI semantic mapping --
            log.info("Step 2: AI mapping with Gemini...")
            mapped, missing, confidence = smart_map_fields(fields, user)
            log.info(f"Step 2 result: {len(mapped)} mapped, {len(missing)} missing")

            for k, v in mapped.items():
                log.info(f"  Mapped: {k} -> {repr(v)}")

            session['mapped_data'] = mapped
            session['missing_fields'] = missing
            session['confidence_scores'] = confidence

            # Build label map
            label_map = {}
            for f in fields:
                label_map[f['name']] = f.get('label', f['name'])
            session['label_map'] = label_map

            log.info("Step 3: Redirecting to /preview")
            return redirect('/preview')

        except Exception as e:
            import traceback
            log.error(f"EXCEPTION: {type(e).__name__}: {e}")
            log.error(traceback.format_exc())
            traceback.print_exc()
            flash(f"Error analyzing form: {str(e)}", "error")
            return redirect('/dashboard')

    # GET request — show dashboard
    history = get_form_history(g.current_user_email, limit=5)

    return render_template(
        'dashboard.html',
        history=history,
        profile=user.get('profile', {}),
    )


# ── PREVIEW (unified editable preview + missing fields) ─────────────────────

@form_bp.route('/preview', methods=['GET', 'POST'])
@login_required
def preview():
    if request.method == 'POST':
        # User submitted the edited preview form
        mapped = dict(session.get('mapped_data', {}))
        form_fields = session.get('form_fields', [])
        label_map = session.get('label_map', {})

        # Collect all values from the preview form
        new_profile_fields = []
        profile_updates = {}

        # Build a type lookup for checkbox handling
        type_lookup = {}
        for f in form_fields:
            type_lookup[f['name']] = f.get('type', 'text')

        for key in request.form:
            if key.startswith('entry.') or key.startswith('field_'):
                field_type = type_lookup.get(key, 'text')

                if field_type == 'checkbox':
                    # Checkboxes: getlist returns all checked values
                    vals = request.form.getlist(key)
                    vals = [v.strip() for v in vals if v.strip()]
                    if vals:
                        mapped[key] = vals
                else:
                    val = request.form.get(key, '').strip()
                    if val:
                        mapped[key] = val

                # Check if this was a missing/edited field — save to profile
                old_val = session.get('mapped_data', {}).get(key)
                current_val = mapped.get(key)
                if current_val and (not old_val or old_val != current_val):
                    label = label_map.get(key, key)
                    new_profile_fields.append(label)
                    # For checkboxes, save as comma-separated string
                    if isinstance(current_val, list):
                        profile_updates[label] = ', '.join(current_val)
                    else:
                        profile_updates[label] = current_val

        # Save new fields to profile
        if profile_updates:
            update_user_profile(g.current_user_email, profile_updates)

        session['mapped_data'] = mapped
        session['new_profile_fields'] = new_profile_fields

        return redirect('/autofill')

    # GET — render the editable preview
    mapped_data = session.get('mapped_data', {})
    missing_fields = session.get('missing_fields', [])
    confidence_scores = session.get('confidence_scores', {})
    label_map = session.get('label_map', {})
    form_fields = session.get('form_fields', [])

    # Build a unified list of all fields for the preview
    preview_fields = []

    # Add mapped fields
    for key, value in mapped_data.items():
        conf = confidence_scores.get(key, 'high')
        label = label_map.get(key, key)
        field_meta = next((f for f in form_fields if f['name'] == key), {})
        preview_fields.append({
            'name': key,
            'label': label,
            'value': value,
            'confidence': conf,
            'source': 'profile',
            'type': field_meta.get('type', 'text'),
            'options': field_meta.get('options', []),
        })

    # Add missing fields (no value)
    for field in missing_fields:
        preview_fields.append({
            'name': field['name'],
            'label': field.get('label', field['name']),
            'value': '',
            'confidence': None,
            'source': 'missing',
            'type': field.get('type', 'text'),
            'options': field.get('options', []),
        })

    return render_template(
        'preview.html',
        preview_fields=preview_fields,
        total_mapped=len(mapped_data),
        total_missing=len(missing_fields),
        total_fields=len(preview_fields),
    )


# ── AUTOFILL ─────────────────────────────────────────────────────────────────

@form_bp.route('/autofill')
@login_required
def autofill():
    form_url = session.get('form_url')
    mapped_data = session.get('mapped_data')

    if not form_url or not mapped_data:
        flash("Missing form URL or data. Please start again.", "error")
        return redirect('/dashboard')

    form_fields = session.get('form_fields', [])
    prefill_url = build_prefill_url(form_url, mapped_data, form_fields)

    if not prefill_url:
        flash("Could not build pre-fill URL. Please try again.", "error")
        return redirect('/dashboard')

    # Get label map for display
    label_map = session.get('label_map', {})

    # Get new profile fields (for enrichment feedback)
    new_profile_fields = session.get('new_profile_fields', [])

    # Save to form history
    save_form_history(
        g.current_user_email,
        form_url,
        mapped_data,
        label_map,
        new_profile_fields,
    )

    return render_template(
        'autofill_ready.html',
        prefill_url=prefill_url,
        mapped_data=mapped_data,
        label_map=label_map,
        new_profile_fields=new_profile_fields,
    )


# ── HISTORY ──────────────────────────────────────────────────────────────────

@form_bp.route('/history')
@login_required
def history():
    form_history = get_form_history(g.current_user_email, limit=50)
    return render_template('history.html', history=form_history)


@form_bp.route('/refill/<int:index>')
@login_required
def refill(index):
    """Re-fill a form from history."""
    history = get_form_history(g.current_user_email, limit=50)
    if index < 0 or index >= len(history):
        flash("Invalid history entry.", "error")
        return redirect('/history')

    entry = history[index]
    session['form_url'] = entry.get('form_url', '')
    session['mapped_data'] = entry.get('mapped_data', {})
    session['label_map'] = entry.get('field_labels', {})
    session['form_fields'] = []
    session['confidence_scores'] = {}
    session['missing_fields'] = []

    flash("Loaded from history! Review and autofill.", "success")
    return redirect('/preview')


# ── CLEAR DATA ───────────────────────────────────────────────────────────────

@form_bp.route('/clear')
@login_required
def clear_data():
    """Clear all previous form analysis data from session."""
    for key in ['mapped_data', 'missing_fields', 'form_url', 'form_fields',
                'confidence_scores', 'label_map', 'new_profile_fields']:
        session.pop(key, None)
    flash("Previous data cleared. You can analyze a new form.", "info")
    return redirect('/dashboard')
