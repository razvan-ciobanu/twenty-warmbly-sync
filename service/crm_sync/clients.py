"""Thin JSON clients for the Twenty REST API and the Warmbly API.

Both raise ApiError for non-2xx answers; get-by-id calls return None on 404.
The engine only uses the methods here, so tests swap in in-memory fakes.
"""
import json
import time
import urllib.error
import urllib.parse
import urllib.request

PLURAL = {"person": "people", "company": "companies", "note": "notes", "noteTarget": "noteTargets"}


class ApiError(Exception):
    def __init__(self, status, body, url=""):
        super().__init__(f"HTTP {status} {url}: {body[:300]}")
        self.status = status
        self.body = body

    @property
    def code(self):
        try:
            return json.loads(self.body).get("code")
        except (ValueError, AttributeError):
            return None


class Http:
    def __init__(self, base, key, min_interval=0.0, timeout=30):
        self.base = base.rstrip("/")
        self.key = key
        self.min_interval = min_interval
        self.timeout = timeout
        self._last = 0.0

    def request(self, method, path, body=None, params=None):
        url = self.base + path
        if params:
            url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(5):
            wait = self._last + self.min_interval - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            req = urllib.request.Request(url, data=data, method=method, headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            })
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read()
                    return json.loads(raw) if raw else None
            except urllib.error.HTTPError as e:
                raw = e.read().decode(errors="replace")
                if e.code == 429 and attempt < 4:
                    time.sleep(min(float(e.headers.get("Retry-After") or 5), 60))
                    continue
                raise ApiError(e.code, raw, f"{method} {path}") from None
        raise AssertionError("unreachable")


class Twenty:
    def __init__(self, url, key):
        self.http = Http(url, key)

    def _one(self, resp):
        # REST answers {"data": {"<operation><Object>": {...}}}
        data = (resp or {}).get("data") or {}
        return next(iter(data.values()), None)

    def get(self, kind, record_id):
        try:
            return self._one(self.http.request("GET", f"/rest/{PLURAL[kind]}/{record_id}"))
        except ApiError as e:
            if e.status in (400, 404):
                return None
            raise

    def find(self, kind, filter=None, order_by=None, limit=100):
        """All records matching a REST filter, following cursors."""
        params = {"limit": limit, "filter": filter, "order_by": order_by}
        while True:
            resp = self.http.request("GET", f"/rest/{PLURAL[kind]}", params=params)
            yield from resp["data"][PLURAL[kind]]
            page = resp.get("pageInfo") or {}
            if not page.get("hasNextPage"):
                return
            params["starting_after"] = page["endCursor"]

    def create(self, kind, data):
        return self._one(self.http.request("POST", f"/rest/{PLURAL[kind]}", body=data))

    def update(self, kind, record_id, patch):
        return self._one(self.http.request("PATCH", f"/rest/{PLURAL[kind]}/{record_id}", body=patch))

    def create_note(self, title, markdown):
        return self.create("note", {"title": title, "bodyV2": {"markdown": markdown}})["id"]

    def attach_note(self, note_id, kind, record_id):
        target = {"person": "targetPersonId", "company": "targetCompanyId"}[kind]
        self.create("noteTarget", {"noteId": note_id, target: record_id})

    def field_types(self, kind):
        """{field name: type} for an object, from the metadata API."""
        query = ("{ objects(paging:{first:500}) { edges { node { nameSingular "
                 "fields(paging:{first:500}) { edges { node { name type } } } } } } }")
        resp = self.http.request("POST", "/metadata", body={"query": query})
        for edge in resp["data"]["objects"]["edges"]:
            node = edge["node"]
            if node["nameSingular"] == kind:
                return {f["node"]["name"]: f["node"]["type"] for f in node["fields"]["edges"]}
        return {}


class Warmbly:
    def __init__(self, url, key, requests_per_minute=55):
        self.http = Http(url, key, min_interval=60.0 / max(requests_per_minute, 1))

    def get_contact(self, contact_id):
        try:
            return self.http.request("GET", f"/contacts/{contact_id}")
        except ApiError as e:
            if e.status in (400, 404):
                return None
            raise

    def lookup(self, email):
        return (self.http.request("GET", "/contacts/lookup", params={"email": email}) or {}).get("contact")

    def search(self, body=None, limit=100):
        params = {"limit": str(limit)}
        while True:
            resp = self.http.request("POST", "/contacts/search", body=body or {}, params=params)
            yield from resp.get("data") or []
            page = resp.get("pagination") or {}
            if not page.get("has_more"):
                return
            params["cursor"] = page["next_cursor"]

    def create_contact(self, data):
        return self.http.request("POST", "/contacts", body=[data])[0]

    def patch_contact(self, contact_id, patch):
        return self.http.request("PATCH", f"/contacts/{contact_id}", body=patch)

    def suppressions(self, q=None):
        params = {"limit": 200, "q": q}
        while True:
            resp = self.http.request("GET", "/suppressions", params=params)
            yield from resp.get("data") or []
            page = resp.get("pagination") or {}
            if not page.get("has_more"):
                return
            params["cursor"] = page["next_cursor"]

    def add_suppression(self, email, reason):
        self.http.request("POST", "/suppressions", body={"entries": [{"value": email}], "reason": reason})

    def delete_suppression(self, suppression_id):
        try:
            self.http.request("DELETE", f"/suppressions/{suppression_id}")
        except ApiError as e:
            if e.status != 404:
                raise

    def campaign(self, campaign_id):
        try:
            return self.http.request("GET", f"/campaigns/{campaign_id}")
        except ApiError as e:
            if e.status in (400, 403, 404):
                return None
            raise

    def lead(self, campaign_id, email):
        """The contact's campaign_lead (status, current_step, ...) in one campaign, or None."""
        for c in self.search({"campaign_ids": [campaign_id], "query": email}, limit=5):
            if c.get("email") == email:
                return c.get("campaign_lead")
        return None
