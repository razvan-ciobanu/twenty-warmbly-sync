"""Field mapping between a Twenty record and a Warmbly contact (pure functions).

Both sides are reduced to the same flat "view": a dict of strings (opt_out is a bool,
label a Warmbly label id or None). The engine compares the two views with the snapshot
of the last sync to decide, field by field, which side changed.

Keys: email, first_name, last_name, phone, company, opt_out, label, and "cf:<key>" for
each configured Warmbly custom field.
"""
import re

CORE = ("email", "first_name", "last_name", "phone", "company")
UNSET = object()   # a field the view doesn't manage (feature off)


def get_path(obj, path):
    for part in path.split("."):
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)
    return obj


def text(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def phone_text(phones):
    """"+40737556677" from a Twenty PHONES value."""
    if not isinstance(phones, dict):
        return ""
    number = text(phones.get("primaryPhoneNumber"))
    if not number:
        return ""
    return text(phones.get("primaryPhoneCallingCode")) + number


def keys(cfg):
    out = list(CORE)
    if cfg.do_not_contact_field:
        out.append("opt_out")
    if cfg.label_path:
        out.append("label")
    out += [f"cf:{k}" for k in cfg.custom_fields]
    return out


def twenty_view(cfg, kind, record, company):
    """View of a Twenty person (with its company, or None) or of a company itself."""
    if kind == "person":
        name = record.get("name") or {}
        view = {
            "email": text(get_path(record, "emails.primaryEmail")),
            "first_name": text(name.get("firstName")),
            "last_name": text(name.get("lastName")),
            "phone": phone_text(record.get("phones")),
        }
    else:
        view = {
            "email": text(get_path(record, f"{cfg.company_email_field}.primaryEmail")) if cfg.company_email_field else "",
            "first_name": "",
            "last_name": "",
            "phone": phone_text(record.get(cfg.company_phone_field)) if cfg.company_phone_field else "",
        }
    view["company"] = text((company or {}).get("name"))
    if cfg.do_not_contact_field:
        view["opt_out"] = bool(record.get(cfg.do_not_contact_field))
    sources = {"person": record if kind == "person" else None, "company": company}
    if cfg.label_path:
        value = _scoped(sources, cfg.label_path)
        view["label"] = cfg.label_values.get(text(value)) if value is not None else None
    for key, path in cfg.custom_fields.items():
        view[f"cf:{key}"] = text(_scoped(sources, path))
    return view


def _scoped(sources, path):
    scope, _, rest = path.partition(".")
    return get_path(sources.get(scope), rest)


def warmbly_view(cfg, contact, suppressed):
    """View of a Warmbly contact; suppressed: whether its address is on the suppression list."""
    view = {k: text(contact.get(k)) for k in CORE}
    view["email"] = view["email"].lower()
    if cfg.do_not_contact_field:
        view["opt_out"] = bool(suppressed) or contact.get("subscribed") is False
    if cfg.label_path:
        ours = set(cfg.label_values.values())
        ids = [c.get("id") if isinstance(c, dict) else c for c in contact.get("categories") or []]
        present = [i for i in ids if i in ours]
        # Several of our labels at once is ambiguous: report "no change" via UNSET.
        view["label"] = present[0] if len(present) == 1 else (None if not present else UNSET)
    custom = contact.get("custom_fields") or {}
    for key in cfg.custom_fields:
        view[f"cf:{key}"] = text(custom.get(key))
    return view


def norm(key, value):
    """Comparison form: ignore case in emails, formatting in phones, trailing zeros in numbers."""
    if value is UNSET or isinstance(value, bool) or value is None:
        return value
    if key == "email":
        return value.strip().lower()
    if key == "phone":
        return re.sub(r"[^\d+]", "", value)
    try:
        return repr(float(value)) if key.startswith("cf:") and value else value
    except ValueError:
        return value


def same(key, a, b):
    return norm(key, a) == norm(key, b)


def merge(fields, twenty, warmbly, snapshot, twenty_newer):
    """Agreed values plus the writes each side needs.

    For each field: changed on one side only -> copy it to the other; changed on both
    (to different values) -> the later-modified side wins (twenty_newer(key) -> bool);
    unchanged -> nothing. A field missing from the snapshot counts as changed on Twenty
    (Twenty owns the first version of a contact).
    Returns (merged, to_twenty, to_warmbly).
    """
    merged, to_twenty, to_warmbly = {}, {}, {}
    for key in fields:
        t, w = twenty.get(key), warmbly.get(key)
        if w is UNSET:
            w = snapshot.get(key, t)
        if key not in snapshot:
            s_t, s_w = False, True
        else:
            s = snapshot[key]
            s_t, s_w = same(key, t, s), same(key, w, s)
        if same(key, t, w):
            merged[key] = t
        elif s_t and not s_w:
            merged[key] = to_twenty[key] = w
        elif s_w and not s_t:
            merged[key] = to_warmbly[key] = t
        elif twenty_newer(key):
            merged[key] = to_warmbly[key] = t
        else:
            merged[key] = to_twenty[key] = w
    return merged, to_twenty, to_warmbly


def warmbly_patch(cfg, changes, contact):
    """PATCH /contacts/:id body for changed view fields (opt_out is handled separately)."""
    patch = {k: changes[k] for k in CORE if k in changes}
    custom = {k[3:]: v for k, v in changes.items() if k.startswith("cf:")}
    if custom:
        merged = dict(contact.get("custom_fields") or {}) if contact else {}
        merged.update(custom)
        patch["custom_fields"] = {k: v for k, v in merged.items() if v != ""}
    if "label" in changes:
        ours = set(cfg.label_values.values())
        current = {c.get("id") if isinstance(c, dict) else c for c in (contact or {}).get("categories") or []}
        remove = sorted((current & ours) - {changes["label"]})
        if remove:
            patch["remove_categories"] = remove
        if changes["label"]:
            patch["add_categories"] = [changes["label"]]
    return patch


def new_contact(cfg, view, twenty_ref):
    """POST /contacts body for a contact created from a Twenty view."""
    body = {k: view[k] for k in CORE if view.get(k)}
    custom = {k[3:]: v for k, v in view.items() if k.startswith("cf:") and v}
    custom["twenty_id"] = twenty_ref
    body["custom_fields"] = custom
    if view.get("label"):
        body["categories"] = [view["label"]]
    return body


def twenty_patches(cfg, kind, changes, record, company, field_types):
    """{"person"|"company": PATCH body} for changed view fields coming from Warmbly.

    Composite values are sent whole (copied from the current record with one sub-field
    changed). field_types: {"person": {name: type}, "company": {...}} from the metadata.
    """
    patches = {"person": {}, "company": {}}
    current = {"person": record if kind == "person" else None, "company": company}

    def put(scope, path, value):
        if current[scope] is None:
            return
        top, _, sub = path.partition(".")
        ftype = field_types.get(scope, {}).get(top)
        if sub:
            base = dict(patches[scope].get(top) or current[scope].get(top) or {})
            base[sub] = value
            patches[scope][top] = base
        else:
            patches[scope][top] = _typed(ftype, value)

    if "email" in changes:
        if kind == "person":
            put("person", "emails.primaryEmail", changes["email"])
        elif cfg.company_email_field:
            put("company", f"{cfg.company_email_field}.primaryEmail", changes["email"])
    if kind == "person":
        if "first_name" in changes:
            put("person", "name.firstName", changes["first_name"])
        if "last_name" in changes:
            put("person", "name.lastName", changes["last_name"])
    if "phone" in changes:
        field = "phones" if kind == "person" else cfg.company_phone_field
        if field:
            scope = "person" if kind == "person" else "company"
            base = dict(current[scope].get(field) or {}) if current[scope] else {}
            patches[scope][field] = _phone(changes["phone"], base)
    if "company" in changes and company is not None and changes["company"]:
        patches["company"]["name"] = changes["company"]
    if "opt_out" in changes and cfg.do_not_contact_field:
        patches[kind][cfg.do_not_contact_field] = bool(changes["opt_out"])
    if "label" in changes and changes["label"]:
        reverse = {v: k for k, v in cfg.label_values.items()}
        scope, _, path = cfg.label_path.partition(".")
        put(scope, path, reverse[changes["label"]])
    for key, path in cfg.custom_fields.items():
        if f"cf:{key}" in changes and path != cfg.label_path:
            scope, _, rest = path.partition(".")
            put(scope, rest, changes[f"cf:{key}"])
    return {k: v for k, v in patches.items() if v}


def _typed(ftype, value):
    if ftype == "NUMBER":
        try:
            return float(value) if value != "" else None
        except ValueError:
            return None
    if ftype == "BOOLEAN":
        return value.lower() in ("true", "1", "yes", "da")
    if value == "" and ftype in ("SELECT", "DATE", "DATE_TIME", "NUMBER"):
        return None
    return value


def _phone(value, base):
    """Twenty PHONES from "+40737556677": keep the current calling code when it prefixes the value."""
    digits = re.sub(r"[^\d+]", "", value)
    code = text(base.get("primaryPhoneCallingCode"))
    out = dict(base)
    if code and digits.startswith(code):
        out["primaryPhoneNumber"] = digits[len(code):]
    else:
        out["primaryPhoneNumber"] = digits
        out["primaryPhoneCallingCode"] = ""
        out["primaryPhoneCountryCode"] = ""
    return out
