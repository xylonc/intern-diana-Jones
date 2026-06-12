from bot.db import init_db , get_connection , get_meta , set_meta
from bot.sources.greenhouse import  GreenhouseSource
from bot.config import GREENHOUSE_BOARDS, KEYWORDS
from bot.scoring import matches
from bot.sources.base import Job
from bot.telegram import send_message


def run():
    # Database 
    init_db()
    connection = get_connection()

    #greenhouse.py
    greenhousesource = GreenhouseSource(GREENHOUSE_BOARDS)
    jobs = greenhousesource.fetch()

    #keyword check 
    current = ",".join(sorted(set(KEYWORDS)))
    kw = get_meta(connection,"keyword")
    if kw and kw != current:
        rescanned = connection.execute(
            """
            SELECT id, source, external_id, title FROM jobs WHERE status = 'skipped'
            """
        ).fetchall()
        for rescan in rescanned:
            temp = Job(source=rescan["source"],external_id=rescan["external_id"],title=rescan["title"])
            match = matches(temp,KEYWORDS)
            if match:
                connection.execute(
                    """
                    UPDATE jobs
                    SET status = 'scored'
                    WHERE id = ?
                    """
                    ,
                    (rescan["id"],),
                )
        connection.commit()
    set_meta(connection,"keyword",current)
    
    for j in jobs:
        connection.execute(
            "INSERT OR IGNORE INTO jobs(source, external_id, title, company, url, location) VALUES(?, ?, ?, ?, ?, ?)",
            (j.source, j.external_id, j.title, j.company, j.url, j.location)
        ) 
    connection.commit()

    #scoring
    entries = connection.execute(
        """
        SELECT id, source, external_id, title FROM jobs WHERE Status = 'new'
        """
    ).fetchall()
    for entry in entries:
        temp = Job(source=entry["source"],external_id=entry["external_id"],title=entry["title"])
        match = matches(temp,KEYWORDS)
        if match:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'scored'
                WHERE id = ?
                """
                ,
                (entry["id"],),
            )
        else:
            connection.execute(
                """
                UPDATE jobs
                SET status = 'skipped'
                WHERE id = ?
                """
                ,
                (entry['id'],),
            )
    connection.commit()

    # notify (digest: batch jobs into messages under Telegram's ~4096-char limit)
    scored = connection.execute(
        "SELECT id, title, company, url FROM jobs WHERE status = 'scored'"
    ).fetchall()

    MAX_CHARS = 4000          # safety margin under Telegram's ~4096 limit
    SEP = "\n\n"              # blank line between jobs in a message

    # Phase 1: group scored jobs into chunks that each fit under MAX_CHARS.
    # Each chunk is a list of (id, blurb) pairs.
    chunks = [] #each chunk is one big message
    current = [] #staging area
    current_len = 0
    for x in scored:
        blurb = f"🔔 {x['title']}\n🏢 {x['company']}\n🔗 {x['url']}"
        #when current is not empty, and the total length exceeds we add this chunk and clear 
        #the staging area
        if current and current_len + len(blurb) + len(SEP) > MAX_CHARS:
            chunks.append(current)
            current = [] #reset staging area
            current_len = 0 #reset length counter
        current.append((x["id"], blurb))
        current_len += len(blurb) + len(SEP)
    if current:
        chunks.append(current)

    # Phase 2: send each chunk, then mark THAT chunk's jobs notified (per-chunk commit).
    for chunk in chunks:
        message = SEP.join(blurb for (job_id, blurb) in chunk)
        send_message(message)
        for (job_id, blurb) in chunk:
            connection.execute(
                "UPDATE jobs SET status = 'notified' WHERE id = ?",
                (job_id,),
            )
        connection.commit()

#seeding
def seed():
    init_db()
    connection = get_connection()
    greenhousesource = GreenhouseSource(GREENHOUSE_BOARDS)
    seen = greenhousesource.fetch()
    for j in seen:
        connection.execute(
            "INSERT OR IGNORE INTO jobs(source, external_id, title, company, url, location,status) VALUES(?, ?, ?, ?, ?, ?, ?)",
            (j.source, j.external_id, j.title, j.company, j.url, j.location,"seen")
        ) 
    connection.commit()