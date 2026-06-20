import time

from bot.db import init_db, get_connection, get_meta, set_meta
from bot.sources.greenhouse import GreenhouseSource
from bot.sources.lever import LeverSource
from bot.sources.ashby import AshbySource
from bot.config import GREENHOUSE_BOARDS, LEVER_COMPANIES, ASHBY_BOARDS
from bot.scoring import matches
from bot.sources.base import Job
from bot.telegram import send_message, get_updates

MAX_CHARS = 4000          # safety margin under Telegram's ~4096-char message limit
SEP = "\n\n"              # blank line between jobs in a digest
LOCATION_KEYWORD = "singapore"   # global: keep only roles whose location contains this

MAX_KEYWORDS = 20         # cap on how many comma-separated keywords a user may register
MAX_KEYWORDS_LEN = 200    # cap on total characters in the stored keyword list

RATE_LIMIT = 5            # max /keyword messages accepted per chat, per window
RATE_WINDOW = 60          # rate-limit window length, in seconds


def _fetch_all() -> list[Job]:
    """Fetch + normalize jobs from every configured source (Greenhouse, Lever, Ashby)."""
    sources = [
        GreenhouseSource(GREENHOUSE_BOARDS),
        LeverSource(LEVER_COMPANIES),
        AshbySource(ASHBY_BOARDS),
    ]
    jobs: list[Job] = []
    for src in sources:
        jobs.extend(src.fetch())
    # global location filter: keep only roles whose location matches LOCATION_KEYWORD
    return [j for j in jobs if LOCATION_KEYWORD in j.location.lower()]


HELP_TEXT = (
    "👋 I send alerts for fresh internship roles.\n"
    "Set the keywords you want with, e.g.:\n"
    "/keyword intern, backend, python\n"
    "Send it again any time to update them."
)

def _over_rate_limit(connection, chat_id) -> bool:
    now = int(time.time())
    key = f"rl:{chat_id}"
    stored = get_meta(connection, key)
    if stored is None:
        window_start, count = now, 0
    else:
        window_start, count = (int(x) for x in stored.split(":"))
        if now - window_start >= RATE_WINDOW:   # window expired -> open a fresh one
            window_start, count = now, 0

    count += 1
    set_meta(connection, key, f"{window_start}:{count}")

    if count == RATE_LIMIT + 1:                 
        send_message(
            f"⏳ Too many keyword updates — I accept at most {RATE_LIMIT} a minute. "
            "Please try again shortly.",
            chat_id,
        )
    return count > RATE_LIMIT


def _process_registrations(connection) -> None:
    """Self-registration via the bot. /start replies with help; /keyword <list>
    upserts the sender's keywords (the chat id is read straight from their message).
    The last update_id is stored in `meta` so messages aren't processed twice."""
    offset = int(get_meta(connection, "tg_offset") or 0)
    for u in get_updates(offset):
        offset = max(offset, u["update_id"] + 1)
        message = u.get("message") or {}
        chat_id = (message.get("chat") or {}).get("id")
        text = (message.get("text") or "").strip()
        if chat_id is None or not text:
            continue
        chat_id = str(chat_id)
        if text.startswith("/start"):
            send_message(HELP_TEXT, chat_id)
        elif text.startswith("/keyword"):
            if _over_rate_limit(connection, chat_id):
                continue
            kw = text[len("/keyword"):].strip()
            # Normalize the same way the matcher will: split on commas, drop blanks.
            # This is also our "empty-after-strip" guard -- "/keyword  , ,," -> [].
            parts = [k.strip() for k in kw.split(",") if k.strip()]
            cleaned = ", ".join(parts)
            if not parts:
                send_message(
                    "I didn't catch any keywords. Usage: /keyword intern, backend, python",
                    chat_id,
                )
            elif len(parts) > MAX_KEYWORDS:
                send_message(
                    f"That's {len(parts)} keywords, but the limit is {MAX_KEYWORDS}. "
                    "Please send a shorter list.",
                    chat_id,
                )
            elif len(cleaned) > MAX_KEYWORDS_LEN:
                send_message(
                    f"Your keyword list is too long ({len(cleaned)} characters); "
                    f"the limit is {MAX_KEYWORDS_LEN}. Please shorten it.",
                    chat_id,
                )
            else:
                connection.execute(
                    "INSERT INTO users(tele_chat_id, keywords) VALUES(?, ?) "
                    "ON CONFLICT(tele_chat_id) DO UPDATE SET keywords = excluded.keywords",
                    (chat_id, cleaned),
                )
                send_message(f"✅ Registered! You'll get alerts for: {cleaned}", chat_id)
    set_meta(connection, "tg_offset", str(offset))
    connection.commit()

def register():
    init_db()
    connection = get_connection()
    try:
        _process_registrations(connection)   # pick up new /start, /keyword messages
    except Exception as e:
        print(f"[register] skipped: {type(e).__name__}: {e}")
    finally:
        connection.close()


def run():
    init_db()
    connection = get_connection()
    jobs = _fetch_all()
    for j in jobs:
        connection.execute(
            "INSERT OR IGNORE INTO jobs(source, external_id, title, company, description, url, location) "
            "VALUES(?, ?, ?, ?, ?, ?, ?)",
            (j.source, j.external_id, j.title, j.company, j.description, j.url, j.location),
        )
    connection.commit()

    
    users = connection.execute(
        "SELECT id, tele_chat_id, keywords FROM users"
    ).fetchall()

    for user in users:
        # Isolate each user: a failure here (e.g. send_message raising because this
        # user blocked the bot) must not starve the users after them in the list.
        try:
            # this user's keywords are stored as a comma-string -> clean lowercase list
            user_keywords = [k.strip().lower() for k in user["keywords"].split(",") if k.strip()]
            candidates = connection.execute(
                """
                SELECT id, source, external_id, title, company, description, url
                FROM jobs
                WHERE status = 'new'
                  AND id NOT IN (SELECT job_id FROM notifications WHERE user_id = ?)
                """,
                (user["id"],),
            ).fetchall()

            matched = []
            for row in candidates:
                job = Job(source=row["source"], external_id=row["external_id"], title=row["title"], description=row["description"])
                if matches(job, user_keywords):
                    matched.append(row)
            if not matched:
                continue

            #we add new information into staging, once staging is filled we send into chunks
            #chunks is what we send the user, staging is then cleared and used to psuh information in
            #until limit again then pushed as a new chunk
            chunks = []
            staging = []
            staging_len = 0
            for row in matched:
                snippet = (row["description"] or "").strip().replace("\n", " ").replace("\r", " ")
                if len(snippet) > 200:
                    snippet = snippet[:200].rstrip() + "…"
                blurb = f"🔔 {row['title']}\n🏢 {row['company']}\n🔗 {row['url']}"
                if snippet:
                    blurb += f"\n📝 {snippet}"
                if staging and staging_len + len(blurb) + len(SEP) > MAX_CHARS:
                    chunks.append(staging)
                    staging = []
                    staging_len = 0
                staging.append((row["id"], blurb))
                staging_len += len(blurb) + len(SEP)
            #this staging is to push any last bits not hit to the maximum
            if staging:
                chunks.append(staging)

            # send each chunk to THIS user, THEN log each job in notifications (send-then-log).
            # Commit per chunk so a crash re-sends at most the in-flight chunk.
            for chunk in chunks:
                message = SEP.join(blurb for (job_id, blurb) in chunk)
                send_message(message, user["tele_chat_id"])
                for (job_id, blurb) in chunk:
                    connection.execute(
                        "INSERT OR IGNORE INTO notifications(user_id, job_id) VALUES(?, ?)",
                        (user["id"], job_id),
                    )
                connection.commit()
        except Exception as e:
            # roll back any half-built transaction so the next user starts clean;
            # the unsent jobs stay out of `notifications`, so they retry next run.
            connection.rollback()
            print(f"[notify] user {user['id']} failed: {type(e).__name__}: {e}")
            continue

    connection.close()


def seed():
    """One-time: record all currently-open jobs as 'seen' (no alerts), so the bot
    only alerts on jobs that appear AFTER setup."""
    init_db()
    connection = get_connection()
    seen = _fetch_all()
    for j in seen:
        connection.execute(
            "INSERT OR IGNORE INTO jobs(source, external_id, title, company, description, url, location, status) "
            "VALUES(?, ?, ?, ?, ?, ?, ?, ?)",
            (j.source, j.external_id, j.title, j.company, j.description, j.url, j.location, "seen"),
        )
    connection.commit()
    connection.close()
