"""Sync behavior against in-memory Twenty and Warmbly (spec crm-sync)."""
from conftest import HOTEL, RESTAURANT, Env


def setup_restaurant(env, email="ana@bistro.ro"):
    company = env.twenty.add_company("Bistro", tip="RESTAURANT", domain="https://bistro.ro", phone="737000111")
    person = env.twenty.add_person(email, company_id=company["id"])
    env.engine.sync_twenty("person", person["id"])
    return company, person


# Twenty contacts present in Warmbly

def test_new_person_becomes_one_contact_with_mapped_fields(env):
    company, person = setup_restaurant(env)
    c = env.contact_of("person", person["id"])
    assert (c["email"], c["first_name"], c["last_name"], c["company"]) == ("ana@bistro.ro", "Ana", "Pop", "Bistro")
    assert [x["id"] for x in c["categories"]] == [RESTAURANT]
    assert c["custom_fields"] == {"city": "București", "domain": "https://bistro.ro", "google_rating": "4.5",
                                  "type": "RESTAURANT", "job_title": "Manager", "twenty_id": f"person:{person['id']}"}
    assert env.twenty.records["person"][person["id"]]["warmblyContactId"] == c["id"]
    assert len(env.warmbly.contacts) == 1
    assert env.quiet("person", person["id"]) == (0, 0)


def test_company_generic_address_is_its_own_contact(env):
    company = env.twenty.add_company("Hotel Lux", email="rezervari@hotel.ro", tip="HOTEL", phone="737556677")
    env.engine.sync_twenty("company", company["id"])
    c = env.contact_of("company", company["id"])
    assert (c["email"], c["company"], c["phone"], c["first_name"]) == ("rezervari@hotel.ro", "Hotel Lux", "+40737556677", "")
    assert [x["id"] for x in c["categories"]] == [HOTEL]
    assert env.twenty.records["company"][company["id"]]["warmblyContactId"] == c["id"]


def test_company_address_shared_with_a_person_syncs_only_the_person(env):
    company = env.twenty.add_company("Hotel Lux", email="office@hotel.ro", tip="HOTEL")
    person = env.twenty.add_person("office@hotel.ro", company_id=company["id"])
    env.engine.sync_twenty("company", company["id"])
    env.engine.sync_twenty("person", person["id"])
    assert len(env.warmbly.contacts) == 1
    assert env.contact_of("person", person["id"]) is not None
    assert env.store.link_by_twenty("company", company["id"]) is None


def test_company_change_in_twenty_updates_all_its_contacts(env):
    company, ana = setup_restaurant(env)
    ion = env.twenty.add_person("ion@bistro.ro", first="Ion", company_id=company["id"])
    env.engine.sync_twenty("person", ion["id"])
    env.twenty.edit("company", company["id"], tipProspect="HOTEL", address={"addressCity": "Cluj"})
    env.store.accept_event("tw-1", "twenty", __import__("crm_sync.server", fromlist=["x"]).twenty_jobs(
        {"eventName": "company.updated", "record": {"id": company["id"]}}))
    env.drain()
    for p in (ana, ion):
        c = env.contact_of("person", p["id"])
        assert [x["id"] for x in c["categories"]] == [HOTEL]
        assert c["custom_fields"]["city"] == "Cluj"


# Linked by id, not by email

def test_email_changed_in_twenty_patches_the_same_contact(env):
    company, person = setup_restaurant(env)
    cid = env.contact_of("person", person["id"])["id"]
    env.twenty.edit("person", person["id"], emails={"primaryEmail": "ana.pop@bistro.ro"})
    env.engine.sync_twenty("person", person["id"])
    assert list(env.warmbly.contacts) == [cid]
    assert env.warmbly.contacts[cid]["email"] == "ana.pop@bistro.ro"


def test_company_email_change_keeps_the_contact(env):
    company = env.twenty.add_company("Hotel Lux", email="office@hotel.ro", tip="HOTEL")
    env.engine.sync_twenty("company", company["id"])
    cid = env.contact_of("company", company["id"])["id"]
    env.twenty.edit("company", company["id"], emails={"primaryEmail": "rezervari@hotel.ro"})
    env.engine.sync_twenty("company", company["id"])
    assert list(env.warmbly.contacts) == [cid]
    assert env.warmbly.contacts[cid]["email"] == "rezervari@hotel.ro"


def test_email_changed_in_warmbly_updates_twenty(env):
    company, person = setup_restaurant(env)
    c = env.contact_of("person", person["id"])
    env.warmbly.edit(c["id"], email="ana.new@bistro.ro")
    env.engine.sync_warmbly(c["id"])
    assert env.twenty.records["person"][person["id"]]["emails"]["primaryEmail"] == "ana.new@bistro.ro"


def test_email_collision_is_reported_and_nothing_merges(env):
    company, ana = setup_restaurant(env)
    ion = env.twenty.add_person("ion@bistro.ro", first="Ion", company_id=company["id"])
    env.engine.sync_twenty("person", ion["id"])
    env.twenty.records["person"][ion["id"]]["emails"]["primaryEmail"] = "ana@bistro.ro"   # bypasses the UI check
    env.engine.sync_twenty("person", ion["id"])
    assert len(env.warmbly.contacts) == 2
    assert env.contact_of("person", ion["id"])["email"] == "ion@bistro.ro"
    assert env.store.stats()["errors"] == 1


# Two-way edits without loops

def test_edit_in_warmbly_reaches_twenty_and_echo_stops(env):
    company, person = setup_restaurant(env)
    c = env.contact_of("person", person["id"])
    env.warmbly.edit(c["id"], last_name="Popescu")
    env.engine.sync_warmbly(c["id"])
    assert env.twenty.records["person"][person["id"]]["name"]["lastName"] == "Popescu"
    assert env.quiet("person", person["id"]) == (0, 0)
    env.engine.sync_warmbly(c["id"])
    assert env.quiet("person", person["id"]) == (0, 0)


def test_conflicting_edits_later_one_wins(env):
    company, person = setup_restaurant(env)
    c = env.contact_of("person", person["id"])
    env.twenty.edit("person", person["id"], name={"lastName": "Twenty"})
    env.warmbly.edit(c["id"], last_name="Warmbly")      # later
    env.engine.sync_twenty("person", person["id"])
    assert env.twenty.records["person"][person["id"]]["name"]["lastName"] == "Warmbly"
    assert env.warmbly.contacts[c["id"]]["last_name"] == "Warmbly"


def test_company_field_edited_in_warmbly_fans_out(env):
    company, ana = setup_restaurant(env)
    ion = env.twenty.add_person("ion@bistro.ro", first="Ion", company_id=company["id"])
    env.engine.sync_twenty("person", ion["id"])
    c = env.contact_of("person", ana["id"])
    env.warmbly.edit(c["id"], categories=[{"id": HOTEL, "title": "Hotel"}])
    env.engine.sync_warmbly(c["id"])
    env.drain()
    assert env.twenty.records["company"][company["id"]]["tipProspect"] == "HOTEL"
    assert [x["id"] for x in env.contact_of("person", ion["id"])["categories"]] == [HOTEL]
    assert env.contact_of("person", ion["id"])["custom_fields"]["type"] == "HOTEL"


def test_custom_field_edit_in_warmbly_updates_the_company(env):
    company, person = setup_restaurant(env)
    c = env.contact_of("person", person["id"])
    env.warmbly.edit(c["id"], custom_fields={"city": "Iași", "google_rating": "4.8"})
    env.engine.sync_warmbly(c["id"])
    rec = env.twenty.records["company"][company["id"]]
    assert rec["address"] == {"addressCity": "Iași", "addressStreet1": "Str. 1"}
    assert rec["ratingGoogle"] == 4.8


def test_lost_webhook_is_repaired_by_reconciliation(env):
    company, person = setup_restaurant(env)
    env.engine.reconcile()
    env.twenty.edit("person", person["id"], name={"firstName": "Anca"})     # no webhook delivered
    env.engine.reconcile()
    assert env.contact_of("person", person["id"])["first_name"] == "Anca"


def test_reconciliation_picks_up_new_records(env):
    company = env.twenty.add_company("Bistro", tip="RESTAURANT")
    person = env.twenty.add_person("ana@bistro.ro", company_id=company["id"])
    result = env.engine.reconcile(full=True)
    assert result["failed"] == 0
    assert env.contact_of("person", person["id"])["email"] == "ana@bistro.ro"


# Deletion

def test_delete_in_twenty_removes_from_campaigns_and_keeps_the_contact(env):
    company, person = setup_restaurant(env)
    c = env.contact_of("person", person["id"])
    env.warmbly.edit(c["id"], campaigns=[{"id": "camp-1"}])
    env.twenty.delete("person", person["id"])
    env.engine.sync_twenty("person", person["id"])
    assert env.warmbly.contacts[c["id"]]["campaigns"] == []
    assert env.store.link_by_twenty("person", person["id"])["active"] == 0
    env.twenty.restore("person", person["id"])
    env.engine.sync_twenty("person", person["id"])
    link = env.store.link_by_twenty("person", person["id"])
    assert (link["active"], link["warmbly_id"]) == (1, c["id"])


def test_delete_in_warmbly_recreates_the_contact_unenrolled(env):
    company, person = setup_restaurant(env)
    old = env.contact_of("person", person["id"])["id"]
    env.warmbly.delete_contact(old)
    env.engine.sync_twenty("person", person["id"])
    c = env.contact_of("person", person["id"])
    assert c["id"] != old and c["campaigns"] == [] and c["email"] == "ana@bistro.ro"
    assert env.twenty.records["person"][person["id"]]["warmblyContactId"] == c["id"]


# Opt-outs

def test_opt_out_set_and_cleared_in_twenty(env):
    company, person = setup_restaurant(env)
    env.twenty.edit("person", person["id"], doNotContact=True)
    env.engine.sync_twenty("person", person["id"])
    assert [s["email"] for s in env.warmbly.sups] == ["ana@bistro.ro"]
    assert env.contact_of("person", person["id"])["subscribed"] is False
    assert env.quiet("person", person["id"]) == (0, 0)
    env.twenty.edit("person", person["id"], doNotContact=False)
    env.engine.sync_twenty("person", person["id"])
    assert env.warmbly.sups == []
    assert env.contact_of("person", person["id"])["subscribed"] is True


def test_opt_out_set_and_cleared_in_warmbly(env):
    company, person = setup_restaurant(env)
    env.warmbly.suppress("ana@bistro.ro", source="unsubscribe")
    env.engine.reconcile()
    rec = env.twenty.records["person"][person["id"]]
    assert rec["doNotContact"] is True
    assert env.twenty.notes_for("person", person["id"])[-1][0] == "Do not contact — set in Warmbly (unsubscribe)"
    env.warmbly.delete_suppression(env.warmbly.sups[0]["id"])
    env.engine.reconcile()
    assert env.twenty.records["person"][person["id"]]["doNotContact"] is False
    assert env.twenty.notes_for("person", person["id"])[-1][0] == "Do not contact — lifted in Warmbly"


# Replies and unsubscribes

def reply_event(email, contact_id="", event_id="ev-1"):
    return {"id": event_id, "event_type": "campaign.reply_received",
            "data": {"contact_email": email, "contact_id": contact_id, "campaign_id": "camp-1",
                     "subject": "Re: Ofertă", "snippet": "Da, sunați-mă", "intent": "interested", "thread_id": "th-9"}}


def deliver(env, event):
    from crm_sync.server import warmbly_jobs
    return env.store.accept_event(f"warmbly:{event['id']}", "warmbly", warmbly_jobs(event))


def test_reply_from_known_contact_adds_one_note(env):
    company, person = setup_restaurant(env)
    cid = env.contact_of("person", person["id"])["id"]
    assert deliver(env, reply_event("ana@bistro.ro", cid))
    assert not deliver(env, reply_event("ana@bistro.ro", cid))       # retried delivery
    env.drain()
    notes = env.twenty.notes_for("person", person["id"])
    assert [t for t, _ in notes] == ["Reply — horeca-2026-11 / step1"]
    assert "Da, sunați-mă" in notes[0][1] and "https://outreach.example/app/unibox/all/th-9" in notes[0][1]
    assert len(env.twenty.records["person"]) == 1


def test_reply_from_unknown_address_creates_person_at_matching_company(env):
    company, person = setup_restaurant(env)
    deliver(env, reply_event("chef@bistro.ro"))
    env.drain()
    new = [p for p in env.twenty.records["person"].values() if p["emails"]["primaryEmail"] == "chef@bistro.ro"]
    assert len(new) == 1 and new[0]["companyId"] == company["id"]
    assert env.twenty.notes_for("person", new[0]["id"])
    assert env.contact_of("person", new[0]["id"]) is not None


def test_twenty_down_then_up_note_once(env):
    company, person = setup_restaurant(env)
    deliver(env, reply_event("ana@bistro.ro", env.contact_of("person", person["id"])["id"]))
    env.twenty.down = True
    assert env.worker.step()                   # fails, stays queued with a backoff
    assert env.store.stats()["failing_jobs"] == 1
    env.twenty.down = False
    env.drain()
    assert len(env.twenty.notes_for("person", person["id"])) == 1


def test_note_not_duplicated_when_attach_fails_after_create(env):
    company, person = setup_restaurant(env)
    deliver(env, reply_event("ana@bistro.ro", env.contact_of("person", person["id"])["id"]))
    original = env.twenty.attach_note
    calls = {"n": 0}

    def flaky(*a):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("timeout")
        return original(*a)
    env.twenty.attach_note = flaky
    assert env.worker.step()                   # note created, attach fails
    env.drain()
    assert len(env.twenty.notes) == 1
    assert len(env.twenty.notes_for("person", person["id"])) == 1


def test_unsubscribe_event_sets_do_not_contact_and_notes(env):
    company, person = setup_restaurant(env)
    cid = env.contact_of("person", person["id"])["id"]
    env.warmbly.suppress("ana@bistro.ro", source="unsubscribe")
    deliver(env, {"id": "ev-u", "event_type": "campaign.unsubscribed",
                  "data": {"contact_email": "ana@bistro.ro", "contact_id": cid, "campaign_id": "camp-1", "source": "link"}})
    env.drain()
    assert env.twenty.records["person"][person["id"]]["doNotContact"] is True
    titles = [t for t, _ in env.twenty.notes_for("person", person["id"])]
    assert titles == ["Unsubscribed — horeca-2026-11 (link)"]


def test_contact_created_by_hand_in_warmbly_is_linked_to_twenty(env):
    company, person = setup_restaurant(env)
    c = env.warmbly.create_contact({"email": "nou@bistro.ro", "first_name": "Nou"})
    deliver(env, {"id": "ev-c", "event_type": "contact.created", "data": {"contact_id": c["id"]}})
    env.drain()
    new = [p for p in env.twenty.records["person"].values() if p["emails"]["primaryEmail"] == "nou@bistro.ro"]
    assert len(new) == 1 and new[0]["companyId"] == company["id"]
    assert env.contact_of("person", new[0]["id"])["id"] == c["id"]


# Optional fields

def test_stock_twenty_without_app_fields(tmp_path):
    env = Env(tmp_path, with_app=False)
    assert env.cfg.link_field is None and env.cfg.do_not_contact_field is None and env.cfg.company_email_field is None
    company = env.twenty.add_company("Bistro", tip="RESTAURANT")
    person = env.twenty.add_person("ana@bistro.ro", company_id=company["id"])
    env.engine.reconcile(full=True)
    c = env.contact_of("person", person["id"])
    assert c["custom_fields"]["twenty_id"] == f"person:{person['id']}"
    assert "warmblyContactId" not in env.twenty.records["person"][person["id"]]
    deliver(env, reply_event("ana@bistro.ro", c["id"]))
    env.drain()
    assert env.twenty.notes_for("person", person["id"])
    assert env.quiet("person", person["id"]) == (0, 0)


def test_conflicting_edits_twenty_later_wins(env):
    company, person = setup_restaurant(env)
    c = env.contact_of("person", person["id"])
    env.warmbly.edit(c["id"], last_name="Warmbly")
    env.twenty.edit("person", person["id"], name={"lastName": "Twenty"})   # later
    env.engine.sync_warmbly(c["id"])
    assert env.twenty.records["person"][person["id"]]["name"]["lastName"] == "Twenty"
    assert env.warmbly.contacts[c["id"]]["last_name"] == "Twenty"


# Only marked records

def test_unmarked_person_is_not_synced(env):
    company = env.twenty.add_company("Bistro", tip="RESTAURANT", sync=False)
    person = env.twenty.add_person("ana@bistro.ro", company_id=company["id"])
    env.engine.reconcile(full=True)
    assert env.warmbly.contacts == {}


def test_marked_person_of_unmarked_company_is_synced_alone(env):
    company = env.twenty.add_company("Hotel Lux", email="office@hotel.ro", tip="HOTEL", sync=False)
    person = env.twenty.add_person("ana@hotel.ro", company_id=company["id"], sync=True)
    env.engine.reconcile(full=True)
    assert [c["email"] for c in env.warmbly.contacts.values()] == ["ana@hotel.ro"]


def test_marking_a_company_syncs_its_address_and_people(env):
    from crm_sync.server import twenty_jobs
    company = env.twenty.add_company("Hotel Lux", email="office@hotel.ro", tip="HOTEL", sync=False)
    for email in ("ana@hotel.ro", "ion@hotel.ro"):
        env.twenty.add_person(email, company_id=company["id"])
    env.engine.reconcile(full=True)
    assert env.warmbly.contacts == {}
    env.twenty.edit("company", company["id"], syncToWarmbly=True)           # the "Sync to Warmbly" button
    env.store.accept_event("tw-m", "twenty", twenty_jobs({"eventName": "company.updated", "record": {"id": company["id"]}}))
    env.drain()
    assert sorted(c["email"] for c in env.warmbly.contacts.values()) == ["ana@hotel.ro", "ion@hotel.ro", "office@hotel.ro"]


def test_company_mark_without_webhook_reaches_people_by_reconciliation(env):
    company = env.twenty.add_company("Hotel Lux", tip="HOTEL", sync=False)
    person = env.twenty.add_person("ana@hotel.ro", company_id=company["id"])
    env.engine.reconcile(full=True)
    env.twenty.edit("company", company["id"], syncToWarmbly=True)
    env.engine.reconcile()
    assert env.contact_of("person", person["id"]) is not None


def test_unmarking_retires_but_keeps_the_contact(env):
    company, person = setup_restaurant(env)
    c = env.contact_of("person", person["id"])
    env.warmbly.edit(c["id"], campaigns=[{"id": "camp-1"}])
    env.twenty.edit("company", company["id"], syncToWarmbly=False)          # "Stop syncing to Warmbly"
    env.engine.reconcile()
    assert env.warmbly.contacts[c["id"]]["campaigns"] == []
    assert env.store.link_by_twenty("person", person["id"])["active"] == 0
    env.twenty.edit("person", person["id"], syncToWarmbly=True)
    env.engine.reconcile()
    link = env.store.link_by_twenty("person", person["id"])
    assert (link["active"], link["warmbly_id"]) == (1, c["id"])


def test_record_matched_from_warmbly_gets_marked(env):
    company = env.twenty.add_company("Bistro", tip="RESTAURANT", domain="https://bistro.ro", sync=False)
    person = env.twenty.add_person("ana@bistro.ro", company_id=company["id"])
    c = env.warmbly.create_contact({"email": "ana@bistro.ro"})
    env.engine.sync_warmbly(c["id"])
    assert env.twenty.records["person"][person["id"]]["syncToWarmbly"] is True
    assert env.contact_of("person", person["id"])["id"] == c["id"]
    deliver(env, reply_event("nou@bistro.ro"))
    env.drain()
    new = next(p for p in env.twenty.records["person"].values() if p["emails"]["primaryEmail"] == "nou@bistro.ro")
    assert new["syncToWarmbly"] is True and env.contact_of("person", new["id"]) is not None
