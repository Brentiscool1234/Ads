# LocalAds Manager

Internal tool for running Google Ads for local-business clients: multi-account
dashboard, a strategy engine taught on a local-business playbook (not Google's
recommendations), a human review queue, and an agent chat layer.

## What it does

- **Multi-account** — each client account has its own vertical, service area,
  target CPA, and mode.
- **Two modes per account**
  - **Review** (default): the strategy engine queues *change proposals* with
    written reasoning; you approve, edit-then-approve, or reject.
  - **Automatic**: pre-vetted, non-budget changes apply on their own (capped,
    cooled-down, audit-logged). Toggle per client.
- **Budgets are immutable** — no mode, no user flow, and no agent path can
  change a campaign budget. Hard-blocked in the API gateway
  (`backend/app/ads/gateway.py`), covered by tests.
- **Strategy engine** — rules from [docs/PLAYBOOK.md](docs/PLAYBOOK.md):
  phrase/exact only, presence-based geo, partners/display off, negative
  keyword mining, evidence-gated pausing, capped bid moves. Google's
  recommendations are never auto-applied.
- **Campaign builder** — creates search campaigns with the playbook enforced
  as validation; campaigns start paused for human review.
- **Reports & audits** — per-account performance CSV and a markdown audit
  (findings + change history) for client communication.
- **Agent** — chat layer (Claude) driving the same guarded tools.

## Running it

Requires Python 3.10 or newer (tested on 3.10 and 3.11).

### Windows

Double-click **`backend\setup.bat`**. It creates the virtual environment,
installs everything, starts the server, and opens the dashboard. Run it again
any time to start the app.

If you would rather type the commands yourself:

```bat
cd C:\path\to\Ads\backend
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m uvicorn app.main:app
```

Use `py -3` rather than `python`. On most Windows machines the bare `python`
command is intercepted by a Microsoft Store shortcut that does nothing.

### macOS / Linux

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://localhost:8000 — the dashboard is served by the backend.

Always install into a virtual environment (the `.venv` steps above). Installing
into a system-wide Python is what causes most of the setup problems below.

By default the app uses a **mock Google Ads backend** with two seeded demo
accounts, so everything works end-to-end without API credentials. Add the
seeded accounts from the dashboard ("Add account") with customer IDs
`111-222-3333` (plumbing) or `444-555-6666` (dental), then hit **Sync &
analyze** to see the engine produce its first review queue.

Agent chat needs `LOCALADS_ANTHROPIC_API_KEY` set; everything else works
without it.

## Tests

```sh
cd backend && python -m pytest tests/
```

## Troubleshooting setup

**`pip install` crashes with a traceback mentioning `googletrans`, `httpcore`,
or `pkg_resources`** — this is a broken Python installation, not a problem with
this project. It happens when a stray script named after a real package (most
often `google.py`) has been saved into the Python install directory. Python
imports that file instead of the real package, and pip crashes before it can do
anything.

The fix is to rename that file so Python stops picking it up. Renaming rather
than deleting keeps it around in case it was something you wrote:

```bat
ren "%LOCALAPPDATA%\Programs\Python\Python310\google.py" google_stray.py.bak
```

Confirm it worked — this should report "File Not Found":

```bat
dir "%LOCALAPPDATA%\Programs\Python\Python310\google.py"
```

Then run `setup.bat` again. The same applies to any stray file shadowing a
package name — `email.py`, `json.py`, `random.py`, and so on.

**`'python' is not recognized`, or Windows offers to install it from the
Microsoft Store** — Windows ships a placeholder `python` command that opens the
Store instead of running Python. Use `py -3` instead of `python`, or run
`setup.bat`, which handles this for you.

**`'uvicorn' is not recognized`** — the dependencies were never installed
(usually because of one of the two problems above), or they were installed into
a different Python than the one you are running. Run `setup.bat`, which installs
and launches using the same interpreter.

## Going live with the real Google Ads API

1. Apply for a developer token (Basic Access) from a Manager (MCC) account.
   The design document for the application is in
   `docs/LocalAds-Manager-Design-Document.pdf`.
2. Create OAuth credentials and link client accounts under the MCC.
3. Implement `GoogleAdsClientImpl` against `backend/app/ads/base.py` using the
   `google-ads` library, and set `LOCALADS_ADS_CLIENT=google`. Nothing above
   the gateway changes.

## Layout

```
backend/app/ads/        client interface, mock backend, guarded gateway
backend/app/strategy/   playbook rules + engine (review vs automatic)
backend/app/services/   sync, proposals, campaign builder, reports
backend/app/api.py      REST API
backend/app/agent.py    agent chat (Claude tool-use loop over the same guards)
frontend/               dashboard (no build step; served by FastAPI)
docs/PLAYBOOK.md        the strategy the engine is taught
```
