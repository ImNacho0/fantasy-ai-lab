import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, create_engine
from sqlalchemy import pool

from alembic import context

# Add repository root to python path so we can import src.fantasy_ai_lab
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fantasy_ai_lab.config import settings
from fantasy_ai_lab.database.connection import Base
# Make sure models are imported so metadata is populated
from fantasy_ai_lab.database.models import (
    SimulationJob, Simulation, League, Manager, Team, Player, Roster, Lineup,
    Matchday, Market, Transaction, Bid, Event, Snapshot, Decision, Situation,
    Outcome, Strategy, StrategyVersion, Reward
)

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Dynamically set the sqlalchemy.url in alembic config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Use our database URL directly
    connectable = create_engine(settings.DATABASE_URL, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
