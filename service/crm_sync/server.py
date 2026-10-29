"""Webhook endpoints, the worker thread and the reconciliation timer.

  python -m crm_sync serve        webhooks + worker + reconciliation
  python -m crm_sync reconcile    one pass now ([--full])
  python -m crm_sync plan         full pass against copies: print the writes it would make
  python -m crm_sync check        which optional Twenty fields exist

POST <any prefix>/twenty   Twenty webhooks: HMAC-SHA256 hex of "<X-Twenty-Webhook-Timestamp>:<body>"
                           in X-Twenty-Webhook-Signature, timestamp (ms) within 5 minutes.
POST <any prefix>/warmbly  Warmbly webhooks: X-Warmbly-Signature "t=<unix>,v1=<hex>" over "<t>.<body>",
                           deduped on X-Warmbly-Event-Id; webhook.test is answered with its challenge.
GET  /healthz
Each request only enqueues jobs (2xx after the commit); the worker re-reads both sides.
"""
import hashlib
import hmac
import json
import logging
import shutil
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import config as config_mod
from .clients import Twenty, Warmbly
from .engine import KINDS, Engine
from .store import Store

log = logging.getLogger("crm_sync")
TOLERANCE = 300
MAX_BODY = 1 << 20


def verify_warmbly(secret, header, body, now=None):
    parts = {}
    for p in (header or "").split(","):
        k, sep, v = p.strip().partition("=")
        if sep:
            parts.setdefault(k, []).append(v)
    try:
        t = int(parts["t"][0])
    except (KeyError, ValueError):
        return False
    if abs((now or time.time()) - t) > TOLERANCE:
        return False
    expected = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, v) for v in parts.get("v1", []))


def verify_twenty(secret, timestamp, signature, body, now=None):
    try:
        t = int(timestamp) / 1000
    except (TypeError, ValueError):
        return False
    if abs((now or time.time()) - t) > TOLERANCE:
        return False
    expected = hmac.new(secret.encode(), f"{timestamp}:".encode() + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def warmbly_jobs(event):
    """Jobs for a Warmbly event (empty for events we don't use)."""
    etype = event.get("event_type")
    data = event.get("data") if isinstance(event.get("data"), dict) else {}
    if etype == "campaign.reply_received":
        return [(f"event:{event['id']}", "reply", {"data": data})]
    if etype == "campaign.unsubscribed":
        return [(f"event:{event['id']}", "unsubscribe", {"data": data})]
    if etype in ("contact.created", "contact.updated", "contact.deleted"):
        contact_id = data.get("contact_id") or data.get("entity_id")
        if contact_id:
            return [(f"warmbly:{contact_id}", "sync_warmbly", {"id": contact_id})]
        return [("reconcile", "reconcile", {})]      # bulk edit: no id, re-read everything changed
    return []


def twenty_jobs(event):
    name, _, _ = (event.get("eventName") or "").partition(".")
    record = event.get("record") or {}
    if name not in KINDS or not record.get("id"):
        return []
    jobs = [(f"sync:{name}:{record['id']}", "sync_twenty", {"kind": name, "id": record["id"]})]
    if name == "company":
        jobs.append((f"fanout:{record['id']}", "fan_out", {"company_id": record["id"]}))
    return jobs


def make_handler(cfg, store):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            log.debug(fmt, *args)

        def _reply(self, status, body=None, headers=None):
            raw = json.dumps(body or {}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/healthz":
                return self._reply(200, store.stats())
            self._reply(404)

        def do_POST(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                return self._reply(413)
            body = self.rfile.read(length)
            path = self.path.split("?")[0].rstrip("/")
            if path.endswith("/warmbly"):
                return self._warmbly(body)
            if path.endswith("/twenty"):
                return self._twenty(body)
            self._reply(404)

        def _warmbly(self, body):
            try:
                event = json.loads(body)
            except ValueError:
                return self._reply(400)
            if event.get("event_type") == "webhook.test":
                challenge = (event.get("data") or {}).get("challenge", "")
                if cfg.warmbly_webhook_secret and not verify_warmbly(
                        cfg.warmbly_webhook_secret, self.headers.get("X-Warmbly-Signature"), body):
                    return self._reply(401)
                return self._reply(200, {"challenge": challenge}, {"X-Warmbly-Webhook-Challenge": challenge})
            if not cfg.warmbly_webhook_secret:
                return self._reply(503)        # not configured yet: Warmbly retries later
            if not verify_warmbly(cfg.warmbly_webhook_secret, self.headers.get("X-Warmbly-Signature"), body):
                return self._reply(401)
            event_id = self.headers.get("X-Warmbly-Event-Id") or event.get("id")
            if not event_id:
                return self._reply(400)
            event["id"] = event_id
            store.accept_event(f"warmbly:{event_id}", "warmbly", warmbly_jobs(event))
            self._reply(200)

        def _twenty(self, body):
            if not cfg.twenty_webhook_secret:
                return self._reply(503)
            if not verify_twenty(cfg.twenty_webhook_secret, self.headers.get("X-Twenty-Webhook-Timestamp"),
                                 self.headers.get("X-Twenty-Webhook-Signature"), body):
                return self._reply(401)
            try:
                event = json.loads(body)
            except ValueError:
                return self._reply(400)
            nonce = self.headers.get("X-Twenty-Webhook-Nonce") or hashlib.sha256(body).hexdigest()
            store.accept_event(f"twenty:{nonce}", "twenty", twenty_jobs(event))
            self._reply(200)

    return Handler


class Worker:
    """Runs jobs one at a time; schedules reconciliation; writes metrics."""

    def __init__(self, cfg, store, engine):
        self.cfg = cfg
        self.store = store
        self.engine = engine

    def run_job(self, job):
        p = job["payload"]
        kind = job["kind"]
        if kind == "sync_twenty":
            self.engine.sync_twenty(p["kind"], p["id"])
        elif kind == "sync_warmbly":
            self.engine.sync_warmbly(p["id"])
        elif kind == "fan_out":
            for pid in self.engine._people_of(p["company_id"]):
                self.store.enqueue(f"sync:person:{pid}", "sync_twenty", {"kind": "person", "id": pid})
        elif kind == "reply":
            self.engine.handle_reply(job)
        elif kind == "unsubscribe":
            self.engine.handle_unsubscribe(job)
        elif kind == "reconcile":
            self.engine.reconcile(full=p.get("full", False))
        else:
            raise ValueError(f"unknown job kind {kind}")

    def step(self):
        """Run one due job; False if there was none."""
        job = self.store.next_job()
        if job is None:
            return False
        try:
            self.run_job(job)
            self.store.finish(job["id"])
        except Exception as e:
            log.exception("job %s (%s) failed, attempt %d", job["key"], job["kind"], job["attempts"] + 1)
            self.store.fail(job["id"], job["attempts"], f"{type(e).__name__}: {e}")
        return True

    def schedule(self, now=None):
        now = now or time.time()
        last_full = float(self.store.get_meta("last_full_reconcile", 0))
        last = float(self.store.get_meta("reconcile_enqueued_at", 0))
        if now - last_full >= self.cfg.full_reconcile_hours * 3600:
            self.store.enqueue("reconcile", "reconcile", {"full": True})
            self.store.set_meta("reconcile_enqueued_at", now)
        elif now - last >= self.cfg.reconcile_minutes * 60:
            self.store.enqueue("reconcile", "reconcile", {})
            self.store.set_meta("reconcile_enqueued_at", now)

    def write_metrics(self):
        if not self.cfg.metrics_file:
            return
        stats = self.store.stats()
        last = float(self.store.get_meta("last_reconcile_success", 0))
        lines = [f"crm_sync_last_reconcile_success_timestamp_seconds {last:.0f}"]
        lines += [f"crm_sync_{k} {v}" for k, v in stats.items()]
        tmp = self.cfg.metrics_file + ".tmp"
        with open(tmp, "w") as f:
            f.write("\n".join(lines) + "\n")
        shutil.move(tmp, self.cfg.metrics_file)

    def loop(self, stop):
        last_prune = 0
        while not stop.is_set():
            try:
                self.schedule()
                ran = self.step()
                self.write_metrics()
                if time.time() - last_prune > 86400:
                    self.store.prune()
                    last_prune = time.time()
            except Exception:
                log.exception("worker loop")
                ran = False
            if not ran:
                stop.wait(2)


def build(cfg, store=None, twenty=None, warmbly=None):
    twenty = twenty or Twenty(cfg.twenty_url, cfg.twenty_api_key)
    warmbly = warmbly or Warmbly(cfg.warmbly_url, cfg.warmbly_api_key, cfg.warmbly_requests_per_minute)
    store = store or Store(cfg.db_path)
    types = {k: twenty.field_types(k) for k in KINDS}
    for line in config_mod.missing_fields(cfg, types["person"], types["company"]):
        log.warning("Twenty field missing, feature disabled: %s", line)
    return store, Engine(cfg, twenty, warmbly, store, types)


class Recorder:
    """Wraps a client for `plan`: reads pass through, writes are printed and faked."""

    WRITES = {"create", "update", "create_note", "attach_note", "create_contact", "patch_contact",
              "add_suppression", "delete_suppression"}

    def __init__(self, name, inner):
        self._name = name
        self._inner = inner
        self.writes = []
        self._n = 0

    def __getattr__(self, attr):
        target = getattr(self._inner, attr)
        if attr not in self.WRITES:
            return target

        def fake(*args):
            self.writes.append((attr, args))
            print(f"[plan] {self._name}.{attr}{json.dumps(args, ensure_ascii=False, default=str)}")
            self._n += 1
            fake_id = f"00000000-0000-4000-8000-{self._n:012d}"
            if attr == "create":
                return {"id": fake_id, **args[-1]}
            if attr == "create_contact":
                body = args[-1]
                return {**body, "id": fake_id, "subscribed": True, "campaigns": [], "updated_at": "",
                        "categories": [{"id": c} for c in body.get("categories", [])]}
            if attr == "create_note":
                return fake_id
            if attr in ("update", "patch_contact"):
                return None
            return None
        return fake


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cmd = argv[0] if argv else "serve"
    cfg = config_mod.load()
    if cmd == "check":
        twenty = Twenty(cfg.twenty_url, cfg.twenty_api_key)
        missing = config_mod.missing_fields(cfg, twenty.field_types("person"), twenty.field_types("company"))
        print("all configured fields exist" if not missing else "\n".join(f"missing: {m}" for m in missing))
        return 0
    if cmd == "plan":
        with tempfile.TemporaryDirectory() as tmp:
            db = f"{tmp}/plan.db"
            try:
                shutil.copy(cfg.db_path, db)
            except FileNotFoundError:
                pass
            twenty = Recorder("twenty", Twenty(cfg.twenty_url, cfg.twenty_api_key))
            warmbly = Recorder("warmbly", Warmbly(cfg.warmbly_url, cfg.warmbly_api_key, cfg.warmbly_requests_per_minute))
            _, engine = build(cfg, Store(db), twenty, warmbly)
            result = engine.reconcile(full=True)
            print(f"[plan] {result['records']} records, {len(twenty.writes)} Twenty writes, "
                  f"{len(warmbly.writes)} Warmbly writes, {result['failed']} failures; nothing was written")
        return 0
    store, engine = build(cfg)
    if cmd == "reconcile":
        print(engine.reconcile(full="--full" in argv))
        return 0
    if cmd == "serve":
        stop = threading.Event()
        worker = Worker(cfg, store, engine)
        threading.Thread(target=worker.loop, args=(stop,), daemon=True).start()
        server = ThreadingHTTPServer((cfg.listen_host, cfg.listen_port), make_handler(cfg, Store(cfg.db_path)))
        log.info("listening on %s:%d", cfg.listen_host, cfg.listen_port)
        try:
            server.serve_forever()
        finally:
            stop.set()
        return 0
    print(__doc__)
    return 2
