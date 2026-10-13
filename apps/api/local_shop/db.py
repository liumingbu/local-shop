from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .config import Settings


def build_engine(settings: Settings) -> Engine:
    return create_engine(
        settings.database_url.get_secret_value(),
        pool_pre_ping=True,
        pool_timeout=settings.db_pool_timeout_seconds,
        connect_args={
            "connect_timeout": 3,
            "options": (
                f"-c statement_timeout={settings.db_statement_timeout_ms} "
                f"-c lock_timeout={settings.db_lock_timeout_ms}"
            ),
        },
        hide_parameters=True,
    )


def probe_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
