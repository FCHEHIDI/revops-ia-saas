import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncEngine
from alembic import context
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))
from app.common.db import Base  # noqa
from app.config import settings

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata

def get_url():
    return settings.database_url

def run_migrations_offline():
    url = get_url()
    context.configure(
        url=url, target_metadata=target_metadata, literal_binds=True, dialect_opts={"paramstyle": "named"}
    )
    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    connectable = AsyncEngine(
        poolclass=pool.NullPool,
        url=get_url()
    )
    async def do_run_migrations(connection):
        await connection.run_sync(lambda x: context.configure(connection=x, target_metadata=target_metadata))
        await connection.run_sync(lambda _: context.run_migrations())
    asyncio.run(
        do_run_migrations(connectable.connect())
    )

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
