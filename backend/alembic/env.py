"""Use application settings without copying credentials into alembic.ini."""

from sqlalchemy import Connection, create_engine, pool

from alembic import context
from app import models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base

config = context.config
target_metadata = Base.metadata


def run_migrations() -> None:
    if context.is_offline_mode():
        context.configure(
            url=get_settings().database_url.get_secret_value(),
            target_metadata=target_metadata,
            literal_binds=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    # A supplied connection enables isolated migration tests.
    connection = config.attributes.get("connection")
    if connection is not None:
        migrate(connection)
        return
    engine = create_engine(
        get_settings().database_url.get_secret_value(),
        poolclass=pool.NullPool,
        connect_args={"connect_timeout": 5},
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            migrate(connection)
    finally:
        engine.dispose()


def migrate(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


run_migrations()
