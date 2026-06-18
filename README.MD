# intern-diana-jones

A Telegram bot that watches public ATS job boards and pushes fresh internship
alerts to subscribers, filtered by their own keywords. Built for NUS students
hunting Singapore-based internships.

It polls Greenhouse, Lever, and Ashby job boards on a schedule, normalizes every
posting into a common shape, keeps only Singapore intern/short-term roles, and
notifies each user about new roles matching the keywords they registered.

---

## How it works

```
   ATS boards                  pipeline                     subscribers
┌───────────────┐      ┌──────────────────────┐      ┌──────────────────┐
│  Greenhouse   │      │  fetch + normalize    │      │  Telegram users  │
│  Lever        │ ───▶ │  → filter (SG/intern) │ ───▶ │  /start          │
│  Ashby        │      │  → dedup → match → send│      │  /keyword ...    │
└───────────────┘      └──────────────────────┘      └──────────────────┘
                                  │
                                  ▼
                            SQLite (jobs, users, notifications)
```

Each ATS has its own quirks (Lever and Ashby expose a structured employment
type; Greenhouse doesn't, so intern roles are detected from the text). Every
source converts its raw JSON into a single `Job` dataclass, so the rest of the
pipeline never knows or cares which board a role came from. Adding a new board
is a config change, not a code change.

### Design decisions worth calling out

- **Send-then-log ordering.** A notification is sent to Telegram *first*, then
  recorded in the `notifications` table. If the process crashes mid-run, the
  worst case is re-sending the in-flight batch — never silently dropping an
  alert. Duplicate sends are bounded; missed sends are not allowed.
- **Idempotent dedup by construction.** Jobs are deduped with
  `INSERT OR IGNORE` on a `UNIQUE(source, external_id)` constraint; notifications
  use a composite primary key `(user_id, job_id)`. A re-processed job or a
  re-attempted notify is a structural no-op, not something the code has to
  remember to guard against.
- **Per-source failure isolation.** One dead or invalid board token can't sink
  the run — each board fetch is wrapped so a failure is logged and skipped while
  the others proceed.
- **Single shared instance.** One process serves all users (users are rows in a
  `users` table keyed by Telegram chat id) rather than one process per user,
  keeping the memory footprint flat on free-tier hosting.

---

## Watched companies

The bot currently watches these boards (verified to resolve as of June 2026).
Coverage is intentionally broad — fintech, dev-tools/infra, AI, and general
SWE — so it's useful across different tracks, not just one.

**Greenhouse:** stripe, adyen, thunes, databricks, datadog, cloudflare, twilio,
gitlab, dropbox, asana, robinhood, coinbase, brex, gusto

**Lever:** nium, spotify, plaid

**Ashby:** airwallex, mercury, linear, notion, vercel, ramp, runway, replit,
supabase, posthog

### Two things to know about coverage

**1. Empty digests in mid-year are normal — it's the hiring calendar, not a bug.**
Summer internship cycles for tech open roughly **July–October**, with rolling
admissions (roles get filled as applications arrive, so the first applicants win).
If you run the bot in, say, May–June, most boards will legitimately have zero open
intern roles — the previous cycle has closed and the next hasn't opened. The bot's
value is catching roles *the moment they post* once the cycle opens. Don't judge
it by an off-season run.

**2. This bot only sees Greenhouse / Lever / Ashby boards.** Many of the biggest
Singapore intern hirers — Grab, Sea/Shopee, ByteDance/TikTok, GovTech, Singtel/NCS,
HTX, and the local banks — run their own portals or Workday/SmartRecruiters, which
this bot **cannot read**. For those, apply directly on the company's careers page.
Treat this bot as covering one useful slice of the market, not all of it.

### Adding more companies

Boards are just entries in three env vars (`GREENHOUSE_BOARDS`, `LEVER_COMPANIES`,
`ASHBY_BOARDS`) — no code change. Before adding a slug, verify it with
`verify_boards.py` (see that script's header), which reuses the bot's own source
classes to report whether a slug resolves and currently has Singapore roles. A
board that resolves but has no SG role *right now* is still worth adding — the
location filter will surface a SG role automatically the moment one is posted.

After adding boards, **re-run `python main.py seed`** before the next pipeline
pass, or the new boards' existing backlog will be alerted to every subscriber.


## Database

Three tables (plus a small `meta` key/value table for the Telegram poll cursor):

- **`jobs`** — the catalogue of seen postings. `UNIQUE(source, external_id)` is
  the dedup key. A `status` column (`new` / `scored` / `notified` / `skipped` /
  `seen`) tracks lifecycle.
- **`users`** — one row per subscriber: their Telegram `chat_id` and their
  comma-separated keywords.
- **`notifications`** — a join table between users and jobs with a composite
  primary key, which doubles as the per-user send-dedup guard.

---

## Setup

### 1. Prerequisites

- Python 3.10+
- A Telegram bot token from [@BotFather](https://t.me/BotFather)

### 2. Install

```bash
git clone <your-repo-url>
cd intern-diana-jones
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure

Copy the example env file and fill it in:

```bash
cp .env.example .env
```

```ini
# From @BotFather
TELEGRAM_BOT_TOKEN=123456:ABC-your-token-here

# Comma-separated board tokens/slugs for each ATS (see "Adding boards" below)
GREENHOUSE_BOARDS=stripe,adyen
LEVER_COMPANIES=nium
ASHBY_BOARDS=airwallex

# Where the SQLite file lives
DB_PATH=jobs.db
```

### 4. Seed once, before going live

`seed` records every currently-open role as already-seen, so subscribers only
get alerts for roles that appear *after* setup — not a flood of the entire
existing backlog on first run.

```bash
python main.py seed
```

> **Run `seed` again whenever you add new boards.** New boards' current openings
> have never been seen, so without re-seeding they'd be treated as brand-new and
> blasted to every subscriber on the next run.

### 5. Run

```bash
python main.py          # one pipeline pass: fetch → match → notify
```

---

## Using the bot (for subscribers)

1. Open the bot in Telegram and send `/start` — it replies with usage help.
2. Register your keywords:
   ```
   /keyword intern, backend, python
   ```
   Send `/keyword` again any time to replace your keyword set. Keywords match as
   whole words against each role's title and description, case-insensitively.

You'll then receive alerts for new Singapore intern roles that match.

---

## Deployment (cron)

The bot is designed to run as two separate scheduled jobs, because the
interactive path and the batch path have different latency needs:

| Job | Command | Cadence | Responsibility |
|-----|---------|---------|----------------|
| Registration | `python main.py register` | frequent (e.g. every 1 min) | poll Telegram for `/start` and `/keyword`, reply quickly |
| Pipeline | `python main.py` | infrequent (e.g. every 15–30 min) | fetch boards, match, send alerts |

**Critical rule:** only the registration job may poll Telegram for incoming
updates. The Telegram poll cursor (`tg_offset`) has a single-owner contract — if
both jobs polled, they would race on the cursor and silently double-process or
lose registration messages. Keep `_process_registrations` out of the pipeline
entry point.

Example crontab:

```cron
* * * * *   cd /path/to/bot && .venv/bin/python main.py register >> register.log 2>&1
*/15 * * * * cd /path/to/bot && .venv/bin/python main.py >> pipeline.log 2>&1
```

Because both jobs share one SQLite file, set a busy timeout (and optionally WAL
mode) in the connection so a writer waits briefly for the lock instead of
raising `database is locked` on contention.

---

## Adding boards

The bot reads boards from three env vars: `GREENHOUSE_BOARDS`,
`LEVER_COMPANIES`, `ASHBY_BOARDS`. Adding a company means adding its board
slug/token to the right list — no code changes.

**Verify a slug before adding it.** A wrong slug won't crash anything (failures
are isolated and skipped), but it'll silently contribute nothing. Test the
public endpoint first:

| ATS | Verification URL | Good response |
|-----|------------------|---------------|
| Greenhouse | `https://boards-api.greenhouse.io/v1/boards/<slug>/jobs` | `200` + JSON with `jobs` |
| Lever | `https://api.lever.co/v0/postings/<slug>?mode=json` | JSON array |
| Ashby | `https://api.ashbyhq.com/posting-api/job-board/<slug>` | `{"jobs": [...]}` |

After adding boards, re-run `python main.py seed` before the next pipeline pass.

> Note: many companies use ATSs this bot doesn't read (Workday, SmartRecruiters,
> bespoke portals). Only Greenhouse / Lever / Ashby boards are supported.

---

## Project layout

```
bot/
  config.py            # env-driven configuration (board lists, token, db path)
  db.py                # SQLite schema + connection
  pipeline.py          # orchestration: fetch → dedup → match → notify
  scoring.py           # keyword matching (whole-word, regex-safe)
  telegram.py          # send messages / poll updates
  sources/
    base.py            # Job dataclass + Source ABC + intern-type helper
    greenhouse.py
    lever.py
    ashby.py
main.py                # entry points: run pipeline / register / seed
requirements.txt
.env.example
```

---

## Roadmap / non-goals

- **Non-goal:** AI/LLM scoring lives in a *separate* downstream agent that reads
  this bot's SQLite `jobs` table — it is deliberately not embedded here. This bot
  stays keyword-only and deterministic.
- **Non-goal:** auto-applying, in-bot JD chat, multi-region support.
