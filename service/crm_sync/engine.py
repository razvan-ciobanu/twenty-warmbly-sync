"""Sync logic: one Twenty record <-> one Warmbly contact, plus reply/unsubscribe notes.

Everything here runs in the single worker thread, so there is no concurrent access to
either API or to a link. Webhooks only enqueue work; each job re-reads both sides.
"""
import logging
from datetime import datetime, timezone

from . import mapping
from .clients import ApiError

log = logging.getLogger("crm_sync")

KINDS = ("person", "company")


def _ts(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _domain(email):
    return email.rpartition("@")[2].lower()


class SyncError(Exception):
    """A problem that retrying won't fix (shown in metrics, logged once per change)."""


class Engine:
    def __init__(self, cfg, twenty, warmbly, store, field_types):
        self.cfg = cfg
        self.twenty = twenty
        self.warmbly = warmbly
        self.store = store
        self.field_types = field_types   # {"person": {name: type}, "company": {...}}
        self.fields = mapping.keys(cfg)

    # Twenty side ---------------------------------------------------------

    def _load(self, kind, twenty_id, record=None, companies=None):
        """(record, company) or (None, None) if the record is gone or deleted."""
        record = record or self.twenty.get(kind, twenty_id)
        if record is None or record.get("deletedAt"):
            return None, None
        if kind == "company":
            return record, record
        company_id = record.get("companyId")
        company = None
        if company_id:
            if companies is not None and company_id in companies:
                company = companies[company_id]
            else:
                company = self.twenty.get("company", company_id)
                if companies is not None:
                    companies[company_id] = company
        return record, company

    def _shadowed(self, company, email):
        """A company address that one of its people also has: only the person is synced."""
        people = self.twenty.find("person", filter=f'companyId[eq]:"{company["id"]}"')
        return any(mapping.same("email", mapping.get_path(p, "emails.primaryEmail") or "", email) for p in people)

    def _people_of(self, company_id):
        return [p["id"] for p in self.twenty.find("person", filter=f'companyId[eq]:"{company_id}"')]

    # Warmbly side --------------------------------------------------------

    def _suppressions(self, email):
        return [s for s in self.warmbly.suppressions(q=email)
                if s.get("kind") == "email" and mapping.same("email", s.get("email", ""), email)]

    # Main entry points ---------------------------------------------------

    def sync_twenty(self, kind, twenty_id, record=None, companies=None, suppressed=None):
        """Bring one Twenty record and its Warmbly contact in line (create/adopt/retire as needed)."""
        key = f"{kind}:{twenty_id}"
        link = self.store.link_by_twenty(kind, twenty_id)
        record, company = self._load(kind, twenty_id, record, companies)
        view_t = mapping.twenty_view(self.cfg, kind, record, company) if record else None
        if (view_t is None or not view_t["email"]
                or (kind == "company" and not self.cfg.company_email_field)
                or (kind == "company" and self._shadowed(record, view_t["email"]))):
            if link and link["active"]:
                self._retire(link)
            return
        try:
            contact, snapshot = self._contact_for(kind, twenty_id, link, view_t)
            self._merge(kind, record, company, contact, snapshot, view_t, suppressed)
            self.store.clear_error(key)
        except SyncError as e:
            log.warning("%s: %s", key, e)
            self.store.set_error(key, str(e))

    def sync_warmbly(self, contact_id):
        """A Warmbly contact changed: sync its pair, or link/create the Twenty side for a new one."""
        link = self.store.link_by_warmbly(contact_id)
        if link:
            return self.sync_twenty(link["twenty_kind"], link["twenty_id"])
        contact = self.warmbly.get_contact(contact_id)
        if contact is None:
            return
        kind, twenty_id = self._twenty_match(contact)
        if twenty_id is None:
            return
        # Adopt this contact for that record; sync_twenty does the field merge.
        self.store.save_link(kind, twenty_id, contact["id"], {}, active=True)
        self.sync_twenty(kind, twenty_id)

    def _twenty_match(self, contact):
        """The Twenty record for an unlinked Warmbly contact: by twenty_id, by email, or a new person."""
        email = (contact.get("email") or "").lower()
        ref = (contact.get("custom_fields") or {}).get("twenty_id", "")
        kind, _, twenty_id = ref.partition(":")
        if kind in KINDS and twenty_id and self._load(kind, twenty_id)[0]:
            other = self.store.link_by_twenty(kind, twenty_id)
            if other is None or not other["active"]:
                return kind, twenty_id
        matches = self._find_by_email(email)
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            self.store.set_error(f"warmbly:{contact['id']}", f"{email} matches {len(matches)} Twenty records")
            return None, None
        person = self._create_person(email, contact)
        return "person", person["id"]

    def _find_by_email(self, email):
        found = [("person", p["id"]) for p in self.twenty.find("person", filter=f'emails.primaryEmail[eq]:"{email}"')]
        if self.cfg.company_email_field:
            found += [("company", c["id"]) for c in
                      self.twenty.find("company", filter=f'{self.cfg.company_email_field}.primaryEmail[eq]:"{email}"')]
        return found

    def _create_person(self, email, contact=None):
        data = {"emails": {"primaryEmail": email, "additionalEmails": []}}
        if contact:
            data["name"] = {"firstName": contact.get("first_name") or "", "lastName": contact.get("last_name") or ""}
        companies = list(self.twenty.find("company", filter=f'domainName.primaryLinkUrl[ilike]:"%{_domain(email)}%"'))
        if len(companies) == 1:
            data["companyId"] = companies[0]["id"]
        person = self.twenty.create("person", data)
        log.info("created Twenty person %s for %s", person["id"], email)
        return person

    # Pairing -------------------------------------------------------------

    def _contact_for(self, kind, twenty_id, link, view_t):
        """(Warmbly contact, snapshot) for a record that should be synced."""
        if link:
            contact = self.warmbly.get_contact(link["warmbly_id"])
            if contact is not None:
                return contact, (link["snapshot"] if link["active"] else {})
            log.info("%s:%s: Warmbly contact %s is gone, recreating", kind, twenty_id, link["warmbly_id"])
        existing = self.warmbly.lookup(view_t["email"])
        if existing:
            other = self.store.link_by_warmbly(existing["id"])
            if other and (other["twenty_kind"], other["twenty_id"]) != (kind, twenty_id) and other["active"]:
                raise SyncError(f"{view_t['email']} already belongs to {other['twenty_kind']}:{other['twenty_id']}")
            return existing, {}
        contact = self.warmbly.create_contact(mapping.new_contact(self.cfg, view_t, f"{kind}:{twenty_id}"))
        log.info("%s:%s: created Warmbly contact %s", kind, twenty_id, contact["id"])
        return contact, {}

    def _retire(self, link):
        """The Twenty record is gone or has no email: out of every campaign, contact kept."""
        contact = self.warmbly.get_contact(link["warmbly_id"])
        if contact and contact.get("campaigns"):
            self.warmbly.patch_contact(link["warmbly_id"], {"campaigns": []})
        self.store.set_active(link["twenty_kind"], link["twenty_id"], False)
        log.info("%s:%s retired (removed from campaigns)", link["twenty_kind"], link["twenty_id"])

    def _company_scoped(self, kind, key):
        if kind == "company" or key == "company":
            return True
        path = self.cfg.label_path if key == "label" else self.cfg.custom_fields.get(key[3:]) if key.startswith("cf:") else None
        return bool(path and path.startswith("company."))

    def _merge(self, kind, record, company, contact, snapshot, view_t, suppressed):
        twenty_id = record["id"]
        email_now = contact.get("email") or ""
        sups = None
        if suppressed is None and self.cfg.do_not_contact_field:
            sups = self._suppressions(email_now)
            suppressed = bool(sups)
        view_w = mapping.warmbly_view(self.cfg, contact, suppressed)
        contact_ts = _ts(contact.get("updated_at"))

        def twenty_newer(key):
            src = company if self._company_scoped(kind, key) and company else record
            return _ts(src.get("updatedAt")) >= contact_ts

        merged, to_twenty, to_warmbly = mapping.merge(self.fields, view_t, view_w, snapshot, twenty_newer)
        if company is None:
            # A person without a company has nowhere to keep company fields edited in Warmbly.
            for key in [k for k in to_twenty if self._company_scoped(kind, k)]:
                del to_twenty[key]
                merged[key] = view_t.get(key)
        errors = []

        # Warmbly writes
        opt_out = to_warmbly.pop("opt_out", None)
        patch = mapping.warmbly_patch(self.cfg, to_warmbly, contact)
        ref = f"{kind}:{twenty_id}"
        if (contact.get("custom_fields") or {}).get("twenty_id") != ref:
            custom = dict(patch.get("custom_fields") or contact.get("custom_fields") or {})
            custom["twenty_id"] = ref
            patch["custom_fields"] = custom
        if patch:
            try:
                contact = self.warmbly.patch_contact(contact["id"], patch) or contact
            except ApiError as e:
                if e.status != 409 or "email" not in patch:
                    raise
                errors.append(f"cannot change Warmbly email to {patch['email']}: {e.code or 'conflict'}")
                merged["email"] = view_w["email"]
                patch.pop("email")
                if patch:
                    contact = self.warmbly.patch_contact(contact["id"], patch) or contact
        if opt_out is not None:
            self._apply_opt_out(contact["id"], view_t["email"], opt_out, sups)

        # Twenty writes
        patches = mapping.twenty_patches(self.cfg, kind, to_twenty, record, company, self.field_types)
        if self.cfg.link_field and record.get(self.cfg.link_field) != contact["id"]:
            patches.setdefault(kind, {})[self.cfg.link_field] = contact["id"]
        if kind == "company":
            patches.pop("person", None)
        for scope in ("person", "company"):
            if scope not in patches:
                continue
            target = twenty_id if scope == kind else (company or {}).get("id")
            if not target:
                continue
            try:
                self.twenty.update(scope, target, patches[scope])
            except ApiError as e:
                if e.status not in (400, 409):
                    raise
                errors.append(f"Twenty rejected {scope} update {sorted(patches[scope])}: {e.body[:200]}")
                for key in to_twenty:
                    merged[key] = view_t.get(key)
        if "opt_out" in to_twenty:
            self._opt_out_note(kind, twenty_id, view_t["email"], to_twenty["opt_out"], sups)
        if company and any(self._company_scoped(kind, k) for k in to_twenty if k != "opt_out"):
            self._fan_out(company["id"], skip=(kind, twenty_id))

        self.store.save_link(kind, twenty_id, contact["id"], merged, active=True)
        if errors:
            raise SyncError("; ".join(errors))

    def _fan_out(self, company_id, skip):
        """A company field changed from Warmbly: re-sync every other contact of that company."""
        targets = [("person", pid) for pid in self._people_of(company_id)] + [("company", company_id)]
        for kind, rid in targets:
            if (kind, rid) != skip:
                self.store.enqueue(f"sync:{kind}:{rid}", "sync_twenty", {"kind": kind, "id": rid})

    # Opt-outs ------------------------------------------------------------

    def _apply_opt_out(self, contact_id, email, opt_out, sups):
        if opt_out:
            self.warmbly.add_suppression(email, "Twenty: do not contact")
            log.info("suppressed %s (Twenty do-not-contact)", email)
            return
        for s in sups if sups is not None else self._suppressions(email):
            self.warmbly.delete_suppression(s["id"])
            log.info("lifted suppression of %s (source %s)", email, s.get("source"))
        self.warmbly.patch_contact(contact_id, {"subscribed": True})

    def _opt_out_note(self, kind, twenty_id, email, opt_out, sups):
        sups = sups if sups is not None else (self._suppressions(email) if opt_out else [])
        source = ", ".join(sorted({s.get("source") or "?" for s in sups})) or "unsubscribed"
        if opt_out:
            title = f"Do not contact — set in Warmbly ({source})"
            body = f"Warmbly opted out **{email}** (source: {source}). `doNotContact` was set."
        else:
            title = "Do not contact — lifted in Warmbly"
            body = f"The Warmbly suppression of **{email}** was removed; `doNotContact` was cleared."
        self._note(kind, twenty_id, title, body)

    # Events --------------------------------------------------------------

    def _resolve(self, data):
        """(kind, twenty_id) for a Warmbly event's contact, creating the person if needed."""
        contact_id = data.get("contact_id") or ""
        email = (data.get("contact_email") or "").lower()
        if contact_id:
            link = self.store.link_by_warmbly(contact_id)
            if link:
                return link["twenty_kind"], link["twenty_id"]
        matches = self._find_by_email(email) if email else []
        if matches:
            return matches[0]
        if not email:
            raise SyncError(f"event without contact email: {data}")
        return "person", self._create_person(email)["id"]

    def _campaign_name(self, campaign_id):
        if not campaign_id:
            return "no campaign"
        campaign = self.warmbly.campaign(campaign_id)
        return (campaign or {}).get("name") or campaign_id

    def handle_reply(self, job):
        data = job["payload"]["data"]
        kind, twenty_id = job["payload"].get("target") or self._resolve(data)
        job["payload"]["target"] = [kind, twenty_id]
        campaign = self._campaign_name(data.get("campaign_id"))
        step = ""
        if data.get("campaign_id") and data.get("contact_email"):
            lead = self.warmbly.lead(data["campaign_id"], data["contact_email"].lower()) or {}
            current = lead.get("current_step") or {}
            if current.get("position") is not None:
                step = f" / step{int(current['position']) + 1}"
        title = f"Reply — {campaign}{step}"
        lines = [f"**From:** {data.get('contact_email', '')}",
                 f"**Subject:** {data.get('subject', '')}",
                 f"**Intent:** {data.get('ai_intent') or data.get('intent') or '-'}"]
        if data.get("ai_labels"):
            lines.append(f"**Labels:** {', '.join(data['ai_labels'])}")
        link = self.cfg.thread_link(data.get("thread_id"))
        if link:
            lines.append(f"**Thread:** {link}")
        lines += ["", "> " + (data.get("snippet") or "").replace("\n", "\n> ")]
        self._note(kind, twenty_id, title, "\n".join(lines), job)
        self.store.enqueue(f"sync:{kind}:{twenty_id}", "sync_twenty", {"kind": kind, "id": twenty_id})

    def handle_unsubscribe(self, job):
        data = job["payload"]["data"]
        kind, twenty_id = job["payload"].get("target") or self._resolve(data)
        job["payload"]["target"] = [kind, twenty_id]
        source = data.get("source") or "unknown"
        title = f"Unsubscribed — {self._campaign_name(data.get('campaign_id'))} ({source})"
        body = f"**{data.get('contact_email', '')}** unsubscribed (source: {source})."
        self._note(kind, twenty_id, title, body, job)
        if self.cfg.do_not_contact_field:
            self.twenty.update(kind, twenty_id, {self.cfg.do_not_contact_field: True})
            link = self.store.link_by_twenty(kind, twenty_id)
            if link:
                snapshot = dict(link["snapshot"], opt_out=True)
                self.store.save_link(kind, twenty_id, link["warmbly_id"], snapshot, active=bool(link["active"]))
        self.store.enqueue(f"sync:{kind}:{twenty_id}", "sync_twenty", {"kind": kind, "id": twenty_id})

    def _note(self, kind, twenty_id, title, body, job=None):
        """Create a note on the record; with a job, exactly once across retries."""
        state = job["payload"] if job else {}
        if not state.get("note_id"):
            state["note_id"] = self.twenty.create_note(title, body)
            if job:
                self.store.update_payload(job["id"], state)
        if not state.get("note_attached"):
            self.twenty.attach_note(state["note_id"], kind, twenty_id)
            state["note_attached"] = True
            if job:
                self.store.update_payload(job["id"], state)

    # Reconciliation ------------------------------------------------------

    def reconcile(self, full=False, now=None):
        """Re-read both sides (changed since the last run, or everything) and sync what differs."""
        started = now or datetime.now(timezone.utc)
        since = None if full else self.store.get_meta("reconcile_since")
        seen, companies = set(), {}
        suppressed = None
        if self.cfg.do_not_contact_field:
            suppressed = {s["email"].lower() for s in self.warmbly.suppressions() if s.get("kind") == "email"}
        failed = 0

        def run(kind, rid, record=None):
            nonlocal failed
            if (kind, rid) in seen:
                return
            seen.add((kind, rid))
            try:
                if kind == "warmbly":
                    self.sync_warmbly(rid)
                else:
                    sup = None
                    link = self.store.link_by_twenty(kind, rid)
                    if suppressed is not None and link:
                        email = link["snapshot"].get("email", "").lower()
                        sup = email in suppressed
                    self.sync_twenty(kind, rid, record=record, companies=companies, suppressed=sup)
            except Exception as e:  # one record must not stop the pass; retry it as a job
                failed += 1
                log.exception("reconcile %s:%s failed", kind, rid)
                if kind == "warmbly":
                    self.store.enqueue(f"warmbly:{rid}", "sync_warmbly", {"id": rid}, delay=60)
                else:
                    self.store.enqueue(f"sync:{kind}:{rid}", "sync_twenty", {"kind": kind, "id": rid}, delay=60)

        flt = f'updatedAt[gte]:"{since}"' if since else None  # since: ISO UTC with Z
        for kind in KINDS:
            for record in self.twenty.find(kind, filter=flt):
                run(kind, record["id"], record)
            deleted_flt = f'deletedAt[gte]:"{since}"' if since else "deletedAt[is]:NOT_NULL"
            for record in self.twenty.find(kind, filter=deleted_flt):
                run(kind, record["id"], record)
        body = {"updated_after": since} if since else {}
        for contact in self.warmbly.search(body):
            link = self.store.link_by_warmbly(contact["id"])
            if link:
                run(link["twenty_kind"], link["twenty_id"])
            else:
                run("warmbly", contact["id"])
        if suppressed is not None:
            for link in self.store.links():
                if not link["active"]:
                    continue
                email = link["snapshot"].get("email", "").lower()
                if bool(link["snapshot"].get("opt_out")) != (email in suppressed):
                    run(link["twenty_kind"], link["twenty_id"])
        # Overlap by a minute so a change made during this pass is seen again next time.
        overlap = datetime.fromtimestamp(started.timestamp() - 60, timezone.utc)
        self.store.set_meta("reconcile_since", overlap.strftime("%Y-%m-%dT%H:%M:%SZ"))
        if full:
            self.store.set_meta("last_full_reconcile", started.timestamp())
        if failed == 0:
            self.store.set_meta("last_reconcile_success", started.timestamp())
        return {"records": len(seen), "failed": failed}
