from alembic import context
from sqlalchemy import create_engine
from sqlalchemy.pool import NullPool

from app.db.database import configured_database_url


config = context.config
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=configured_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(
        configured_database_url(),
        poolclass=NullPool,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args={"connect_timeout": 10} if configured_database_url().startswith("postgresql+") else {},
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
