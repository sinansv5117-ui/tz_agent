from typing import Literal

from app.db.postgres import get_connection

MessageType = Literal["info", "complaint", "other"]


def save_message(message_type: MessageType, summarized_message: str) -> dict:
    """Store a categorized summary in the exact PostgreSQL `infos` table.

    The user's schema intentionally has no separate message_type column, so
    the category is stored as a prefix inside `message`.
    """
    allowed = {"info", "complaint", "other"}
    if message_type not in allowed:
        raise ValueError("message_type must be one of: info, complaint, other")

    summary = str(summarized_message).strip()
    if not summary:
        raise ValueError("summarized_message cannot be empty")

    stored_message = f"[{message_type.upper()}] {summary}"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO infos (message) VALUES (%s) RETURNING info_id, time, message",
                (stored_message,),
            )
            row = cur.fetchone()

    return {"status": "saved", "info_id": row[0], "time": row[1].isoformat(), "message": row[2]}


def complaint_receiver(message_type: MessageType, summarized_message: str) -> dict:
    return save_message(message_type, summarized_message)
