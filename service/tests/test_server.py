"""Webhook endpoints: signatures, challenge, dedupe, routing to jobs."""
import hashlib
import hmac
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from crm_sync.server import make_handler


@pytest.fixture
def server(env):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(env.cfg, env.store))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/hooks/crm-sync"
    srv.shutdown()


def post(url, body, headers):
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read() or b"{}"), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, {}, {}


def warmbly_headers(secret, body, event_id="ev-1", t=None):
    t = int(t or time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Warmbly-Signature": f"t={t},v1={sig}", "X-Warmbly-Event-Id": event_id}


def twenty_headers(secret, body, t=None):
    ts = str(int((t or time.time()) * 1000))
    sig = hmac.new(secret.encode(), f"{ts}:".encode() + body, hashlib.sha256).hexdigest()
    return {"X-Twenty-Webhook-Timestamp": ts, "X-Twenty-Webhook-Signature": sig, "X-Twenty-Webhook-Nonce": "n1"}


REPLY = json.dumps({"id": "ev-1", "event_type": "campaign.reply_received",
                    "data": {"contact_email": "a@b.ro", "campaign_id": "camp-1"}}).encode()


def test_valid_warmbly_event_is_queued_once(server, env):
    assert post(server + "/warmbly", REPLY, warmbly_headers("wb-secret", REPLY))[0] == 200
    assert post(server + "/warmbly", REPLY, warmbly_headers("wb-secret", REPLY))[0] == 200
    assert env.store.stats()["pending_jobs"] == 1


@pytest.mark.parametrize("headers", [
    {},
    {"X-Warmbly-Signature": "t=1,v1=00", "X-Warmbly-Event-Id": "ev-1"},
    "wrong-secret",
    "stale",
])
def test_forged_or_stale_warmbly_event_is_rejected(server, env, headers):
    if headers == "wrong-secret":
        headers = warmbly_headers("nope", REPLY)
    elif headers == "stale":
        headers = warmbly_headers("wb-secret", REPLY, t=time.time() - 600)
    assert post(server + "/warmbly", REPLY, headers)[0] == 401
    assert env.store.stats()["pending_jobs"] == 0


def test_challenge_is_echoed(server):
    body = json.dumps({"event_type": "webhook.test", "data": {"challenge": "whcg_abc"}}).encode()
    status, payload, headers = post(server + "/warmbly", body, warmbly_headers("wb-secret", body))
    assert status == 200 and payload == {"challenge": "whcg_abc"}
    assert headers["X-Warmbly-Webhook-Challenge"] == "whcg_abc"


def test_unconfigured_secret_defers_events(server, env):
    env.cfg.warmbly_webhook_secret = ""
    assert post(server + "/warmbly", REPLY, warmbly_headers("x", REPLY))[0] == 503


def test_twenty_event_is_verified_and_queued(server, env):
    body = json.dumps({"eventName": "company.updated", "record": {"id": "c1"}}).encode()
    assert post(server + "/twenty", body, twenty_headers("tw-secret", body))[0] == 200
    keys = {r[0] for r in env.store.db.execute("SELECT key FROM jobs")}
    assert keys == {"sync:company:c1", "fanout:c1"}
    assert post(server + "/twenty", body, twenty_headers("bad", body))[0] == 401


def test_unused_events_are_acknowledged(server, env):
    body = json.dumps({"id": "ev-2", "event_type": "campaign.email_sent", "data": {}}).encode()
    assert post(server + "/warmbly", body, warmbly_headers("wb-secret", body, "ev-2"))[0] == 200
    assert env.store.stats()["pending_jobs"] == 0
