import datetime
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON, Table
from sqlalchemy.orm import relationship
from fantasy_ai_lab.database.connection import Base

def get_utc_now():
    return datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

class SimulationJob(Base):
    __tablename__ = 'simulation_jobs'

    id = Column(Integer, primary_key=True)
    status = Column(String(50), default='pending')  # pending, running, completed, failed, partial
    configuration = Column(JSON, nullable=True)     # Store dict config
    seed = Column(Integer, nullable=False)
    leagues_total = Column(Integer, default=1)
    leagues_completed = Column(Integer, default=0)
    matchdays = Column(Integer, default=5)
    current_league_idx = Column(Integer, default=0)
    current_matchday_idx = Column(Integer, default=0)
    checkpoint = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)
    updated_at = Column(DateTime, default=get_utc_now, onupdate=get_utc_now)

    simulations = relationship("Simulation", back_populates="job", cascade="all, delete-orphan")


class Simulation(Base):
    __tablename__ = 'simulations'

    id = Column(Integer, primary_key=True)
    job_id = Column(Integer, ForeignKey('simulation_jobs.id'), nullable=True)
    name = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    job = relationship("SimulationJob", back_populates="simulations")
    leagues = relationship("League", back_populates="simulation", cascade="all, delete-orphan")


class League(Base):
    __tablename__ = 'leagues'

    id = Column(Integer, primary_key=True)
    simulation_id = Column(Integer, ForeignKey('simulations.id'), nullable=True)
    name = Column(String(255), nullable=False)
    status = Column(String(50), default='active')  # active, completed
    matchday = Column(Integer, default=0)
    rules = Column(JSON, nullable=True)
    seed = Column(Integer, nullable=False)
    parent_league_id = Column(Integer, ForeignKey('leagues.id'), nullable=True)  # For fork support
    created_at = Column(DateTime, default=get_utc_now)

    simulation = relationship("Simulation", back_populates="leagues")
    managers = relationship("Manager", back_populates="league", cascade="all, delete-orphan")
    teams = relationship("Team", back_populates="league", cascade="all, delete-orphan")
    players = relationship("Player", back_populates="league", cascade="all, delete-orphan")
    rosters = relationship("Roster", back_populates="league", cascade="all, delete-orphan")
    lineups = relationship("Lineup", back_populates="league", cascade="all, delete-orphan")
    matchdays = relationship("Matchday", back_populates="league", cascade="all, delete-orphan")
    markets = relationship("Market", back_populates="league", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="league", cascade="all, delete-orphan")
    bids = relationship("Bid", back_populates="league", cascade="all, delete-orphan")
    events = relationship("Event", back_populates="league", cascade="all, delete-orphan")
    snapshots = relationship("Snapshot", back_populates="league", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="league", cascade="all, delete-orphan")
    situations = relationship("Situation", back_populates="league", cascade="all, delete-orphan")


class Manager(Base):
    __tablename__ = 'managers'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    name = Column(String(255), nullable=False)
    strategy_type = Column(String(100), default='Balanced')  # Conservative, Aggressive, Trader, PointsMaximizer, LongTerm, Opportunistic, Balanced, Random
    strategy_version = Column(String(50), default='v1.0')
    budget = Column(Float, default=40000000.0)
    points = Column(Float, default=0.0)
    position = Column(Integer, default=1)
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="managers")
    rosters = relationship("Roster", back_populates="manager", cascade="all, delete-orphan")
    lineups = relationship("Lineup", back_populates="manager", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="manager", cascade="all, delete-orphan")
    bids = relationship("Bid", back_populates="manager", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="manager", cascade="all, delete-orphan")
    situations = relationship("Situation", back_populates="manager", cascade="all, delete-orphan")


class Team(Base):
    __tablename__ = 'teams'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    name = Column(String(255), nullable=False)
    external_team_id = Column(String(100), nullable=True)
    level = Column(Integer, default=1)  # 1 to 5 (strength/prestige)
    strength = Column(Float, default=1.0)
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="teams")


class Player(Base):
    __tablename__ = 'players'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    name = Column(String(255), nullable=False)
    position = Column(String(50), nullable=False)  # GK, DF, MF, FW
    club_name = Column(String(255), nullable=False)
    price = Column(Float, default=1000000.0)
    market_value = Column(Float, default=1000000.0)
    xp = Column(Float, default=4.0)  # Expected points per matchday
    form = Column(Float, default=1.0) # performance multiplier
    play_probability = Column(Float, default=1.0)  # probability of starting
    status = Column(String(50), default='healthy')  # healthy, injured_light, injured_grave, suspended, breakout
    status_duration = Column(Integer, default=0)    # how many matchdays remaining in current status
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="players")
    rosters = relationship("Roster", back_populates="player", cascade="all, delete-orphan")
    transactions = relationship("Transaction", back_populates="player", cascade="all, delete-orphan")
    bids = relationship("Bid", back_populates="player", cascade="all, delete-orphan")
    decisions = relationship("Decision", back_populates="player", cascade="all, delete-orphan")


class Roster(Base):
    __tablename__ = 'rosters'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    manager_id = Column(Integer, ForeignKey('managers.id'), nullable=False)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    purchase_price = Column(Float, default=0.0)
    purchase_matchday = Column(Integer, default=0)
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="rosters")
    manager = relationship("Manager", back_populates="rosters")
    player = relationship("Player", back_populates="rosters")


class Lineup(Base):
    __tablename__ = 'lineups'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    manager_id = Column(Integer, ForeignKey('managers.id'), nullable=False)
    matchday_number = Column(Integer, nullable=False)
    formation = Column(String(50), default='4-4-2')  # e.g., 4-4-2, 3-5-2, etc.
    goalkeeper_id = Column(Integer, nullable=True)
    defenders_ids = Column(JSON, nullable=True)       # list of player IDs
    midfielders_ids = Column(JSON, nullable=True)     # list of player IDs
    forwards_ids = Column(JSON, nullable=True)        # list of player IDs
    substitutes_ids = Column(JSON, nullable=True)     # list of player IDs
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="lineups")
    manager = relationship("Manager", back_populates="lineups")


class Matchday(Base):
    __tablename__ = 'matchdays'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    matchday_number = Column(Integer, nullable=False)
    status = Column(String(50), default='pending')  # pending, completed
    simulated_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="matchdays")


class Market(Base):
    __tablename__ = 'markets'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    matchday_number = Column(Integer, nullable=False)
    status = Column(String(50), default='open')  # open, closed
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="markets")


class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    manager_id = Column(Integer, ForeignKey('managers.id'), nullable=False)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    type = Column(String(50), nullable=False)  # BUY, SELL
    amount = Column(Float, nullable=False)
    matchday_number = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="transactions")
    manager = relationship("Manager", back_populates="transactions")
    player = relationship("Player", back_populates="transactions")


class Bid(Base):
    __tablename__ = 'bids'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    manager_id = Column(Integer, ForeignKey('managers.id'), nullable=False)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=False)
    amount = Column(Float, nullable=False)
    matchday_number = Column(Integer, nullable=False)
    status = Column(String(50), default='pending')  # pending, won, lost
    timestamp = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="bids")
    manager = relationship("Manager", back_populates="bids")
    player = relationship("Player", back_populates="bids")


class Event(Base):
    __tablename__ = 'events'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    matchday_number = Column(Integer, nullable=False)
    event_type = Column(String(100), nullable=False) # e.g. STAR_PLAYER_INJURED, SANCTION, PERFORMANCE_BOOST, etc
    target_player_id = Column(Integer, nullable=True)
    target_manager_id = Column(Integer, nullable=True)
    description = Column(Text, nullable=False)
    severity = Column(String(50), default='info')  # info, warning, extreme
    duration = Column(Integer, default=0)
    impact = Column(Float, default=1.0)
    probability = Column(Float, default=0.0)
    uncertainty = Column(Float, default=0.0)
    consequences = Column(JSON, nullable=True)
    recovery = Column(JSON, nullable=True)
    source = Column(String(50), default='random')  # random, scheduled, historical, manual
    is_extreme = Column(Boolean, default=False)
    simulated_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="events")


class Snapshot(Base):
    __tablename__ = 'snapshots'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    matchday_number = Column(Integer, nullable=False)
    snapshot_data = Column(JSON, nullable=False)  # holds complete JSON dump of the state
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="snapshots")


class Decision(Base):
    __tablename__ = 'decisions'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    manager_id = Column(Integer, ForeignKey('managers.id'), nullable=False)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=True)
    matchday_number = Column(Integer, nullable=False)
    action_type = Column(String(50), nullable=False)  # BUY, SELL, HOLD, LINEUP
    amount = Column(Float, nullable=True)
    confidence = Column(Float, default=1.0)
    expected_outcome = Column(JSON, nullable=True)
    available_actions = Column(JSON, nullable=True)
    alternative_actions = Column(JSON, nullable=True)
    situation_id = Column(Integer, ForeignKey('situations.id'), nullable=True)
    strategy_version = Column(String(50), default='v1.0')
    reasoning_factors = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="decisions")
    manager = relationship("Manager", back_populates="decisions")
    player = relationship("Player", back_populates="decisions")
    situation = relationship("Situation", back_populates="decisions", foreign_keys=[situation_id])
    rewards = relationship("Reward", back_populates="decision", cascade="all, delete-orphan")


class Situation(Base):
    __tablename__ = 'situations'

    id = Column(Integer, primary_key=True)
    league_id = Column(Integer, ForeignKey('leagues.id'), nullable=False)
    manager_id = Column(Integer, ForeignKey('managers.id'), nullable=False)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=True)
    matchday_number = Column(Integer, nullable=False)
    state_features = Column(JSON, nullable=False) # Context features
    created_at = Column(DateTime, default=get_utc_now)

    league = relationship("League", back_populates="situations")
    manager = relationship("Manager", back_populates="situations")
    decisions = relationship("Decision", back_populates="situation", foreign_keys="Decision.situation_id")
    outcomes = relationship("Outcome", back_populates="situation", cascade="all, delete-orphan")


class Outcome(Base):
    __tablename__ = 'outcomes'

    id = Column(Integer, primary_key=True)
    decision_id = Column(Integer, ForeignKey('decisions.id'), nullable=True)
    situation_id = Column(Integer, ForeignKey('situations.id'), nullable=True)
    result_data = Column(JSON, nullable=True)
    points_gained = Column(Float, default=0.0)
    wealth_gained = Column(Float, default=0.0)
    created_at = Column(DateTime, default=get_utc_now)

    decision = relationship("Decision", foreign_keys=[decision_id])
    situation = relationship("Situation", back_populates="outcomes", foreign_keys=[situation_id])


class Strategy(Base):
    __tablename__ = 'strategies'

    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    parameters = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)


class StrategyVersion(Base):
    __tablename__ = 'strategy_versions'

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(100), nullable=False)
    version = Column(String(50), nullable=False)
    parameters = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    lifecycle_status = Column(String(50), default='candidate')  # candidate, validated, promoted, archived
    parent_version = Column(String(50), nullable=True)
    promoted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=get_utc_now)


class Reward(Base):
    __tablename__ = 'rewards'

    id = Column(Integer, primary_key=True)
    decision_id = Column(Integer, ForeignKey('decisions.id'), nullable=False)
    points_score = Column(Float, default=0.0)
    wealth_score = Column(Float, default=0.0)
    risk_score = Column(Float, default=0.0)
    total_reward = Column(Float, default=0.0)
    profile_name = Column(String(100), default='balanced')
    created_at = Column(DateTime, default=get_utc_now)

    decision = relationship("Decision", back_populates="rewards")


class Scenario(Base):
    __tablename__ = 'scenarios'

    id = Column(Integer, primary_key=True)
    name = Column(String(120), unique=True, nullable=False)
    description = Column(Text, nullable=True)
    configuration = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=get_utc_now)


class KnowledgeCase(Base):
    __tablename__ = 'knowledge_cases'

    id = Column(Integer, primary_key=True)
    situation_id = Column(Integer, ForeignKey('situations.id'), nullable=False)
    decision_id = Column(Integer, ForeignKey('decisions.id'), nullable=False)
    feature_vector = Column(JSON, nullable=False)
    dataset_name = Column(String(100), default='simulation', nullable=False)
    strategy_name = Column(String(100), nullable=True)
    strategy_version = Column(String(50), nullable=True)
    sample_weight = Column(Float, default=1.0)
    created_at = Column(DateTime, default=get_utc_now)


class Counterfactual(Base):
    __tablename__ = 'counterfactuals'

    id = Column(Integer, primary_key=True)
    decision_id = Column(Integer, ForeignKey('decisions.id'), nullable=False)
    action_type = Column(String(50), nullable=False)
    player_id = Column(Integer, ForeignKey('players.id'), nullable=True)
    result_data = Column(JSON, nullable=False)
    points_delta = Column(Float, default=0.0)
    wealth_delta = Column(Float, default=0.0)
    sample_size = Column(Integer, default=0, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    source = Column(String(50), default='explicit_estimate', nullable=False)
    created_at = Column(DateTime, default=get_utc_now)


class Evaluation(Base):
    __tablename__ = 'evaluations'

    id = Column(Integer, primary_key=True)
    strategy_name = Column(String(100), nullable=False)
    strategy_version = Column(String(50), nullable=False)
    dataset_name = Column(String(100), nullable=False)
    sample_size = Column(Integer, default=0)
    metrics = Column(JSON, nullable=False, default=dict)
    status = Column(String(50), default='candidate')
    created_at = Column(DateTime, default=get_utc_now)


class Tournament(Base):
    __tablename__ = 'tournaments'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    configuration = Column(JSON, nullable=False, default=dict)
    rankings = Column(JSON, nullable=False, default=list)
    status = Column(String(50), default='created')
    created_at = Column(DateTime, default=get_utc_now)
