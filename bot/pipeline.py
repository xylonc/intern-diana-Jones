from bot.db import init_db , get_connection
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

    #notify
    scored = connection.execute(
        """
        SELECT id, title, company , url FROM jobs WHERE status ='scored'
        """
    ).fetchall()
    for x in scored:
        text = (
              f"🔔 New job match\n\n"
              f"{x['title']}\n"
              f"🏢 {x['company']}\n"
              f"🔗 {x['url']}"
          )
        send_message(text)
        connection.execute(
            """
            UPDATE jobs 
            SET status = 'notified'
            WHERE id = ?
            """
            ,
            (x['id'],),
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