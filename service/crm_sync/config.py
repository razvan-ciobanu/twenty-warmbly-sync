"""Configuration: a JSON file (CRM_SYNC_CONFIG) for mappings, the environment for secrets.

Every Twenty field the sync uses besides the standard person fields is optional:
set it to null (or leave it out) and the behavior that needs it is disabled.
See config.example.json for all keys.
"""
import json
import os
from dataclasses import dataclass, field


@dataclass
class Config:
    twenty_url: str
    warmbly_url: str                      # API base, ending in /v1
    twenty_api_key: str = ""
    warmbly_api_key: str = ""
    twenty_webhook_secret: str = ""
    warmbly_webhook_secret: str = ""
    warmbly_app_url: str = ""             # for links to reply threads in notes
    thread_url: str = "{app_url}/app/unibox/all/{thread_id}"
    # Optional Twenty fields (field names; None = feature off).
    company_email_field: str | None = None      # EMAILS on company: company contacts
    company_phone_field: str | None = None      # PHONES on company
    do_not_contact_field: str | None = None     # BOOLEAN on person and company
    link_field: str | None = None               # TEXT on person and company
    # Warmbly custom field -> Twenty path ("person.<field>[.<sub>]" or "company.<field>[.<sub>]").
    custom_fields: dict = field(default_factory=dict)
    # A Twenty value mapped to Warmbly labels: {"field": "<path>", "values": {value: label_id}}.
    label: dict | None = None
    reconcile_minutes: int = 15
    full_reconcile_hours: int = 24
    warmbly_requests_per_minute: int = 55
    db_path: str = "/data/crm-sync.db"
    metrics_file: str | None = None
    listen_host: str = "127.0.0.1"
    listen_port: int = 8092

    @property
    def label_path(self):
        return (self.label or {}).get("field")

    @property
    def label_values(self):
        return (self.label or {}).get("values") or {}

    def thread_link(self, thread_id):
        if not (self.warmbly_app_url and thread_id):
            return ""
        return self.thread_url.format(app_url=self.warmbly_app_url.rstrip("/"), thread_id=thread_id)


def load(path=None, env=None):
    env = os.environ if env is None else env
    path = path or env.get("CRM_SYNC_CONFIG")
    data = {}
    if path:
        with open(path) as f:
            data = json.load(f)
    fields = data.pop("fields", {}) or {}
    cfg = Config(
        twenty_url=data.pop("twenty_url").rstrip("/"),
        warmbly_url=data.pop("warmbly_url").rstrip("/"),
        company_email_field=fields.get("company_email"),
        company_phone_field=fields.get("company_phone"),
        do_not_contact_field=fields.get("do_not_contact"),
        link_field=fields.get("warmbly_contact_id"),
        **data,
    )
    cfg.twenty_api_key = env.get("TWENTY_API_KEY", "")
    cfg.warmbly_api_key = env.get("WARMBLY_API_KEY", "")
    cfg.twenty_webhook_secret = env.get("TWENTY_WEBHOOK_SECRET", "")
    cfg.warmbly_webhook_secret = env.get("WARMBLY_WEBHOOK_SECRET", "")
    for name in ("db_path", "metrics_file", "listen_host"):
        if env.get(name.upper()):
            setattr(cfg, name, env[name.upper()])
    if env.get("LISTEN_PORT"):
        cfg.listen_port = int(env["LISTEN_PORT"])
    return cfg


def missing_fields(cfg, person_fields, company_fields):
    """Disable optional features whose Twenty field doesn't exist; returns what was disabled.

    person_fields / company_fields: {field name: type} from Twenty's metadata.
    """
    disabled = []
    if cfg.company_email_field and cfg.company_email_field not in company_fields:
        disabled.append(f"company.{cfg.company_email_field} (company contacts)")
        cfg.company_email_field = None
    if cfg.company_phone_field and cfg.company_phone_field not in company_fields:
        disabled.append(f"company.{cfg.company_phone_field} (company phone)")
        cfg.company_phone_field = None
    for attr, what in (("do_not_contact_field", "opt-out sync"), ("link_field", "link field")):
        name = getattr(cfg, attr)
        if name and not (name in person_fields and name in company_fields):
            disabled.append(f"{name} on person/company ({what})")
            setattr(cfg, attr, None)
    for key, path in list(cfg.custom_fields.items()):
        if not _path_exists(path, person_fields, company_fields):
            disabled.append(f"{path} (custom field {key})")
            del cfg.custom_fields[key]
    if cfg.label_path and not _path_exists(cfg.label_path, person_fields, company_fields):
        disabled.append(f"{cfg.label_path} (labels)")
        cfg.label = None
    return disabled


def _path_exists(path, person_fields, company_fields):
    scope, _, rest = path.partition(".")
    fields = {"person": person_fields, "company": company_fields}.get(scope)
    return fields is not None and rest.split(".")[0] in fields
