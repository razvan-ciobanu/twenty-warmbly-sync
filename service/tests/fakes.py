"""In-memory Twenty and Warmbly with the same methods as crm_sync.clients."""
import copy
import itertools
import re
import uuid
from datetime import datetime, timedelta, timezone

from crm_sync.clients import ApiError

_clock = itertools.count()
BASE = datetime(2026, 11, 1, tzinfo=timezone.utc)


def tick():
    """A strictly increasing timestamp, shared by both fakes (later call = later edit)."""
    return (BASE + timedelta(seconds=next(_clock))).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _get(obj, path):
    for part in path.split("."):
        obj = (obj or {}).get(part)
    return obj


class FakeTwenty:
    PERSON_FIELDS = {"name": "FULL_NAME", "emails": "EMAILS", "phones": "PHONES", "jobTitle": "TEXT",
                     "companyId": "UUID", "doNotContact": "BOOLEAN", "warmblyContactId": "TEXT",
                     "syncToWarmbly": "BOOLEAN"}
    COMPANY_FIELDS = {"name": "TEXT", "domainName": "LINKS", "address": "ADDRESS", "telefon": "PHONES",
                      "tipProspect": "SELECT", "ratingGoogle": "NUMBER", "emails": "EMAILS",
                      "doNotContact": "BOOLEAN", "warmblyContactId": "TEXT", "syncToWarmbly": "BOOLEAN"}

    def __init__(self, with_app=True):
        self.records = {"person": {}, "company": {}}
        self.notes = []          # (id, title, body)
        self.targets = []        # (note_id, kind, record_id)
        self.down = False
        self.writes = 0
        self.with_app = with_app

    def _check(self):
        if self.down:
            raise ApiError(503, "down")

    # helpers for tests
    def add_company(self, name, email="", tip=None, city="București", domain="", phone="", sync=True, **extra):
        rec = {"name": name, "domainName": {"primaryLinkUrl": domain, "primaryLinkLabel": "", "secondaryLinks": []},
               "address": {"addressCity": city, "addressStreet1": "Str. 1"},
               "telefon": {"primaryPhoneNumber": phone, "primaryPhoneCallingCode": "+40" if phone else "",
                           "primaryPhoneCountryCode": "RO" if phone else "", "additionalPhones": []},
               "tipProspect": tip, "ratingGoogle": 4.5, **extra}
        if self.with_app:
            rec.update(emails={"primaryEmail": email, "additionalEmails": []}, doNotContact=False, warmblyContactId="",
                       syncToWarmbly=sync)
        return self.create("company", rec)

    def add_person(self, email, first="Ana", last="Pop", company_id=None, sync=False, **extra):
        rec = {"name": {"firstName": first, "lastName": last},
               "emails": {"primaryEmail": email, "additionalEmails": []},
               "phones": {"primaryPhoneNumber": "", "primaryPhoneCallingCode": "", "additionalPhones": []},
               "jobTitle": "Manager", "companyId": company_id, **extra}
        if self.with_app:
            rec.update(doNotContact=False, warmblyContactId="", syncToWarmbly=sync)
        return self.create("person", rec)

    def edit(self, kind, rid, **changes):
        """A user edit in the Twenty UI (not counted as a sync write)."""
        rec = self.records[kind][rid]
        for k, v in changes.items():
            if isinstance(v, dict) and isinstance(rec.get(k), dict):
                rec[k] = {**rec[k], **v}
            else:
                rec[k] = v
        rec["updatedAt"] = tick()

    # client API
    def get(self, kind, rid):
        self._check()
        rec = self.records[kind].get(rid)
        if rec is None or rec.get("deletedAt"):
            return None
        return copy.deepcopy(rec)

    def find(self, kind, filter=None, order_by=None, limit=200):
        self._check()
        for rec in list(self.records[kind].values()):
            if self._match(rec, filter):
                yield copy.deepcopy(rec)

    def _match(self, rec, flt):
        if flt is None:
            return not rec.get("deletedAt")
        m = re.fullmatch(r'([\w.]+)\[(\w+)\]:"?(.*?)"?', flt)
        path, op, value = m.groups()
        actual = _get(rec, path)
        if path == "deletedAt":
            if op == "is":
                return actual is not None
            return actual is not None and _dt(actual) >= _dt(value)
        if rec.get("deletedAt"):
            return False
        if op == "eq":
            return (actual or "") == value
        if op == "ilike":
            return value.strip("%").lower() in (actual or "").lower()
        if op == "gte":
            return actual is not None and _dt(actual) >= _dt(value)
        raise NotImplementedError(flt)

    def create(self, kind, data):
        self._check()
        self.writes += 1
        rid = str(uuid.uuid4())
        rec = copy.deepcopy(data)
        rec.update(id=rid, createdAt=tick(), deletedAt=None)
        rec["updatedAt"] = rec["createdAt"]
        if kind in self.records:
            self.records[kind][rid] = rec
        return copy.deepcopy(rec)

    def update(self, kind, rid, patch):
        self._check()
        self.writes += 1
        rec = self.records[kind][rid]
        if "emails" in patch and kind == "person":
            email = patch["emails"]["primaryEmail"]
            if any(_get(p, "emails.primaryEmail") == email and p["id"] != rid for p in self.records["person"].values()):
                raise ApiError(400, '{"messages":["duplicate email"]}')
        rec.update(copy.deepcopy(patch))
        rec["updatedAt"] = tick()
        return copy.deepcopy(rec)

    def delete(self, kind, rid):
        self.records[kind][rid]["deletedAt"] = tick()
        self.records[kind][rid]["updatedAt"] = tick()

    def restore(self, kind, rid):
        self.records[kind][rid]["deletedAt"] = None
        self.records[kind][rid]["updatedAt"] = tick()

    def create_note(self, title, markdown):
        self._check()
        nid = str(uuid.uuid4())
        self.notes.append((nid, title, markdown))
        return nid

    def attach_note(self, note_id, kind, rid):
        self._check()
        self.targets.append((note_id, kind, rid))

    def notes_for(self, kind, rid):
        ids = {n for n, k, r in self.targets if (k, r) == (kind, rid)}
        return [(t, b) for n, t, b in self.notes if n in ids]

    def field_types(self, kind):
        fields = dict(self.PERSON_FIELDS if kind == "person" else self.COMPANY_FIELDS)
        if not self.with_app:
            for name in ("doNotContact", "warmblyContactId", "syncToWarmbly", "emails" if kind == "company" else None):
                fields.pop(name, None)
        return fields


class FakeWarmbly:
    def __init__(self):
        self.contacts = {}
        self.sups = []
        self.campaigns = {"camp-1": {"id": "camp-1", "name": "horeca-2026-11"}}
        self.writes = 0
        self.down = False

    def _check(self):
        if self.down:
            raise ApiError(503, "down")

    # helpers
    def by_email(self, email):
        return next((c for c in self.contacts.values() if c["email"] == email.lower()), None)

    def edit(self, contact_id, **changes):
        """A user edit in the Warmbly UI."""
        c = self.contacts[contact_id]
        for k, v in changes.items():
            if k == "custom_fields":
                c[k] = {**c[k], **v}
            else:
                c[k] = v
        c["updated_at"] = tick()

    def suppress(self, email, source="unsubscribe"):
        self.sups.append({"id": str(uuid.uuid4()), "email": email.lower(), "kind": "email", "source": source})
        c = self.by_email(email)
        if c:
            c["subscribed"] = False
            c["updated_at"] = tick()

    # client API
    def get_contact(self, cid):
        self._check()
        c = self.contacts.get(cid)
        return copy.deepcopy(c) if c else None

    def lookup(self, email):
        self._check()
        c = self.by_email(email)
        return copy.deepcopy(c) if c else None

    def search(self, body=None, limit=200):
        self._check()
        body = body or {}
        for c in list(self.contacts.values()):
            if body.get("updated_after") and _dt(c["updated_at"]) < _dt(body["updated_after"]):
                continue
            yield copy.deepcopy(c)

    def create_contact(self, data):
        self._check()
        self.writes += 1
        existing = self.by_email(data["email"])
        if existing:
            return self.patch_contact(existing["id"], {k: v for k, v in data.items() if k != "email"})
        cid = str(uuid.uuid4())
        self.contacts[cid] = {
            "id": cid, "email": data["email"].lower(), "first_name": data.get("first_name", ""),
            "last_name": data.get("last_name", ""), "company": data.get("company", ""), "phone": data.get("phone", ""),
            "custom_fields": dict(data.get("custom_fields") or {}), "subscribed": True,
            "campaigns": [{"id": x} for x in data.get("campaigns", [])],
            "categories": [{"id": x, "title": x} for x in data.get("categories", [])],
            "updated_at": tick(),
        }
        return copy.deepcopy(self.contacts[cid])

    def patch_contact(self, cid, patch):
        self._check()
        self.writes += 1
        c = self.contacts[cid]
        if "email" in patch:
            other = self.by_email(patch["email"])
            if other and other["id"] != cid:
                raise ApiError(409, '{"code":"contact_email_taken"}')
            c["email"] = patch["email"].lower()
        for k in ("first_name", "last_name", "company", "phone", "subscribed"):
            if k in patch:
                c[k] = patch[k]
        if "custom_fields" in patch:
            c["custom_fields"] = dict(patch["custom_fields"])
        if "campaigns" in patch:
            c["campaigns"] = [{"id": x} for x in patch["campaigns"]]
        ids = [x["id"] for x in c["categories"]]
        ids = [x for x in ids if x not in patch.get("remove_categories", [])] + \
              [x for x in patch.get("add_categories", []) if x not in ids]
        c["categories"] = [{"id": x, "title": x} for x in ids]
        c["updated_at"] = tick()
        return copy.deepcopy(c)

    def delete_contact(self, cid):
        del self.contacts[cid]

    def suppressions(self, q=None):
        self._check()
        for s in list(self.sups):
            if q is None or q.lower() in s["email"]:
                yield dict(s)

    def add_suppression(self, email, reason):
        self._check()
        self.writes += 1
        if not any(s["email"] == email.lower() for s in self.sups):
            self.suppress(email, source="manual")

    def delete_suppression(self, sid):
        self._check()
        self.writes += 1
        s = next((s for s in self.sups if s["id"] == sid), None)
        if s:
            self.sups.remove(s)
            c = self.by_email(s["email"])
            if c:
                c["subscribed"] = True
                c["updated_at"] = tick()

    def campaign(self, cid):
        return self.campaigns.get(cid)

    def lead(self, cid, email):
        return {"status": "replied", "current_step": {"position": 0}}
