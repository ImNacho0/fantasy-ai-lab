from src.fantasy_ai_lab.simulator.engine import SimulationEngine
from src.fantasy_ai_lab.simulator.market import MarketEngine
from src.fantasy_ai_lab.database.models import Bid, Transaction, Roster, Manager, Player

def test_market_resolve_bids(db_session):
    engine = SimulationEngine(seed=300)
    league = engine.create_league(db_session, "Test Market League", seed=300)

    # Get unowned players and a manager
    market_engine = MarketEngine(seed=300)
    candidates = market_engine.get_market_candidates(db_session, league.id)
    assert len(candidates) > 0

    target_player = candidates[0]
    manager = db_session.query(Manager).filter_by(league_id=league.id).first()
    # Boost budget to ensure the bid is valid and affordable
    manager.budget = 50000000.0
    db_session.commit()

    # Place a pending bid
    bid = Bid(
        league_id=league.id,
        manager_id=manager.id,
        player_id=target_player.id,
        amount=target_player.price * 1.1,
        matchday_number=1,
        status="pending"
    )
    db_session.add(bid)
    db_session.commit()

    # Resolve bids
    transactions = market_engine.resolve_bids(db_session, league.id, matchday_num=1)
    assert len(transactions) == 1
    assert transactions[0].type == "BUY"
    assert transactions[0].manager_id == manager.id
    assert transactions[0].player_id == target_player.id

    # Check that bid is marked won
    assert bid.status == "won"

    # Check roster updated
    roster_item = db_session.query(Roster).filter_by(
        manager_id=manager.id,
        player_id=target_player.id
    ).first()
    assert roster_item is not None

def test_market_process_sales(db_session):
    engine = SimulationEngine(seed=310)
    league = engine.create_league(db_session, "Test Sales League", seed=310)

    manager = db_session.query(Manager).filter_by(league_id=league.id).first()
    roster_item = db_session.query(Roster).filter_by(manager_id=manager.id).first()
    player = db_session.query(Player).filter_by(id=roster_item.player_id).first()

    initial_budget = manager.budget
    market_engine = MarketEngine(seed=310)

    # Sell the player
    tx = market_engine.process_sales(
        db=db_session,
        league_id=league.id,
        manager_id=manager.id,
        player_id=player.id,
        sale_price=player.price,
        matchday_num=1
    )

    assert tx is not None
    assert tx.type == "SELL"
    assert manager.budget == initial_budget + player.price

    # Ensure player removed from roster
    roster_check = db_session.query(Roster).filter_by(
        manager_id=manager.id,
        player_id=player.id
    ).first()
    assert roster_check is None
