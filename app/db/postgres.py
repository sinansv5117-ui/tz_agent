from contextlib import contextmanager

from app.config import settings


@contextmanager
def get_connection():
    """Open a PostgreSQL connection only when a DB operation is requested."""
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "PostgreSQL driver is missing. Install dependencies with: pip install -r requirements.txt"
        ) from exc

    conn = psycopg.connect(settings.database_url)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
