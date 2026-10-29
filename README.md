# crm-sync

Two-way sync between [Twenty](https://twenty.com) CRM and
[Warmbly](https://warmbly.com) cold email.

- `service/` — the sync service (contacts, edits, opt-outs, reply notes).
- `twenty-app/` — optional Twenty app adding the fields the service can use.

Design and requirements: OpenSpec change `adopt-warmbly` (design D9, D11;
spec `crm-sync`) in the deployment repository.
