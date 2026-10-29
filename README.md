# twenty-warmbly-sync (crm-sync)

Two-way sync between [Twenty](https://twenty.com) CRM and
[Warmbly](https://github.com/warmbly/warmbly) cold email. Twenty owns your contacts,
Warmbly owns your campaigns; crm-sync keeps the two consistent.

- **Contacts:** the people and companies you mark in Twenty become Warmbly contacts,
  linked by id, so an address changed on either side updates the same contact.
- **Edits both ways:** names, email, phone, company name, a label (e.g. Hotel/Restaurant
  from a Twenty select field) and any custom fields you map. The later edit wins.
- **Opt-outs both ways:** a Twenty "do not contact" flag ↔ the Warmbly suppression list,
  set and cleared from either side.
- **Replies and unsubscribes** become notes on the Twenty record.
- It never creates, starts or sends campaigns.

| Directory | What | License |
|---|---|---|
| [`service/`](service/) | The sync service: Python 3.12, standard library only, SQLite state, one Docker image | Apache-2.0 |
| [`twenty-app/`](twenty-app/) | Optional Twenty app: "Sync to Warmbly" buttons and the fields the service uses | AGPL-3.0-only |

The Twenty app is optional: on a stock Twenty the service syncs every person with an
email and turns off the features whose fields are missing (`python -m crm_sync check`
lists them).

## Quick start

1. Optionally install the Twenty app (see [`twenty-app/README.md`](twenty-app/README.md)).
2. Create a Twenty API key and a Warmbly API key (`READ_CAMPAIGNS | READ_CONTACTS |
   WRITE_CONTACTS`).
3. Copy `service/config.example.json`, set your URLs and mappings, and run the service
   (see [`service/README.md`](service/README.md)); `python -m crm_sync plan` shows every
   write a first sync would make without making it.
4. Point a Twenty webhook (`person.*`, `company.*`) at `https://<host>/…/twenty` and a
   Warmbly webhook (`contact.*`, `campaign.reply_received`, `campaign.unsubscribed`) at
   `https://<host>/…/warmbly`, each with its signing secret.

Tested with Twenty v2.25 and Warmbly v0.6.63.
