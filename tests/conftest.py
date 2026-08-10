import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fantasy_ai_lab.database.connection import Base
from fantasy_ai_lab.database.models import (
    SimulationJob, Simulation, League, Manager, Team, Player, Roster, Lineup,
    Matchday, Market, Transaction, Bid, Event, Snapshot, Decision, Situation,
    Outcome, Strategy, StrategyVersion, Reward
)

@pytest.fixture(scope="function")
def db_session():
    """
    Creates a fresh, isolated in-memory SQLite database and session for each test.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
