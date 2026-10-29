import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from crm_sync.config import Config  # noqa: E402
from crm_sync.server import Worker, build  # noqa: E402
from crm_sync.store import Store  # noqa: E402
from fakes import FakeTwenty, FakeWarmbly  # noqa: E402

HOTEL, RESTAURANT = "label-hotel", "label-restaurant"


def make_cfg(tmp_path):
    return Config(
        twenty_url="http://twenty", warmbly_url="http://warmbly/v1", warmbly_app_url="https://outreach.example",
        company_email_field="emails", company_phone_field="telefon",
        do_not_contact_field="doNotContact", link_field="warmblyContactId",
        custom_fields={"city": "company.address.addressCity", "domain": "company.domainName.primaryLinkUrl",
                       "google_rating": "company.ratingGoogle", "type": "company.tipProspect",
                       "job_title": "person.jobTitle"},
        label={"field": "company.tipProspect", "values": {"HOTEL": HOTEL, "RESTAURANT": RESTAURANT}},
        db_path=str(tmp_path / "state.db"), twenty_webhook_secret="tw-secret", warmbly_webhook_secret="wb-secret",
    )


class Env:
    def __init__(self, tmp_path, with_app=True):
        self.cfg = make_cfg(tmp_path)
        self.twenty = FakeTwenty(with_app=with_app)
        self.warmbly = FakeWarmbly()
        self.store = Store(self.cfg.db_path)
        _, self.engine = build(self.cfg, self.store, self.twenty, self.warmbly)
        self.worker = Worker(self.cfg, self.store, self.engine)

    def drain(self, limit=200):
        """Run every queued job (delayed retries too), like a worker given enough time."""
        for _ in range(limit):
            job = self.store.next_job(now=1e12)
            if job is None:
                return
            self.worker.run_job(job)
            self.store.finish(job["id"])
        raise AssertionError("jobs never drained")

    def contact_of(self, kind, rid):
        link = self.store.link_by_twenty(kind, rid)
        return self.warmbly.contacts.get(link["warmbly_id"]) if link else None

    def quiet(self, kind, rid):
        """Sync again and return (Twenty writes, Warmbly writes) it made."""
        t, w = self.twenty.writes, self.warmbly.writes
        self.engine.sync_twenty(kind, rid)
        return self.twenty.writes - t, self.warmbly.writes - w


@pytest.fixture
def env(tmp_path):
    return Env(tmp_path)
