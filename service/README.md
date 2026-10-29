# crm-sync service

Keeps Twenty CRM and Warmbly consistent. Twenty owns contacts, Warmbly owns campaigns.

- Every Twenty person with an email, and every company with a primary email (optional
  field), is one Warmbly contact. Records are linked by id, so an address change updates
  the same contact.
- Names, email, phone, company name, a label (e.g. Hotel/Restaurant from a select field)
  and mapped custom fields sync both ways. A field changed on one side is copied to the
  other; changed on both, the later edit wins. A company field edited on one Warmbly
  contact updates the Twenty company and from there its other contacts.
- `doNotContact` ↔ Warmbly suppression list, set and cleared from either side, with a note.
- Replies and unsubscribes become notes on the Twenty record (a person is created for an
  unknown address, attached to the company whose domain matches).
- A record deleted in Twenty leaves every campaign; its contact is kept. A contact deleted
  in Warmbly is recreated, unenrolled. The service never creates or starts campaigns.

Twenty webhooks (`person.*`, `company.*`) and Warmbly webhooks (`contact.*`,
`campaign.reply_received`, `campaign.unsubscribed`) only queue work; a worker re-reads both
sides and diffs against the last synced snapshot, which also stops echo loops. A
reconciliation pass (every 15 min, a full one daily) repairs anything a lost webhook missed.

Standard library only (Python 3.12), state in SQLite.

## Configuration

`CRM_SYNC_CONFIG` points to a JSON file like `config.example.json`. Secrets come from the
environment: `TWENTY_API_KEY`, `WARMBLY_API_KEY`, `TWENTY_WEBHOOK_SECRET`,
`WARMBLY_WEBHOOK_SECRET`. Every field under `fields`, `custom_fields` and `label` is
optional: at startup the service checks Twenty's metadata and disables whatever depends on
a missing field (`python -m crm_sync check` lists them). The fields in `../twenty-app` are
the ones `config.example.json` expects.

The Warmbly key needs `READ_CAMPAIGNS | READ_CONTACTS | WRITE_CONTACTS`. Warmbly labels
can't be listed with an API key, so label ids go in the config.

## Commands

    python -m crm_sync serve            # webhooks on LISTEN_HOST:LISTEN_PORT + worker
    python -m crm_sync plan             # full pass with writes printed, not made
    python -m crm_sync reconcile [--full]
    python -m crm_sync check

Webhook paths end in `/twenty` and `/warmbly` (e.g. `https://host/hooks/crm-sync/twenty`).

## Tests

    python -m pytest tests     # in-memory Twenty and Warmbly, no network
