# Warmbly Sync — Twenty app

The Twenty side of [crm-sync](../README.md). It adds, all optional for the service:

| Object | Field | Type | Used for |
|---|---|---|---|
| Person, Company | `syncToWarmbly` | Boolean | Which records are synced (a marked company syncs its own address and all its people) |
| Person, Company | `doNotContact` | Boolean | ↔ Warmbly suppression list |
| Person, Company | `warmblyContactId` | Text | The linked Warmbly contact (read-only for people, set by the service) |
| Company | `emails` | Emails | The company's own address (e.g. `office@…`) as a contact |

plus "Sync to Warmbly" / "Stop syncing to Warmbly" in the command menu for the selected
people or companies, and places the fields on the record pages. Its role can only read and
update people and companies.

## Install

Node 24 and Yarn 4 (see `.nvmrc`, `package.json`). With a Twenty API key for your
workspace:

    yarn install
    yarn twenty remote:add        # your Twenty URL and API key
    yarn twenty plan              # what the install would change
    yarn twenty app:publish --private
    yarn twenty app:install

Built with `twenty-sdk` 2.23 against Twenty v2.25.

## License

AGPL-3.0-only (see `LICENSE`).
