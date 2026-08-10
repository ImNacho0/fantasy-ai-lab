import random
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.fantasy_ai_lab.database.models import Player, Roster, Manager, Transaction, Bid, Market

class MarketEngine:
    def __init__(self, seed: int = 123):
        self.seed = seed
        self.rng = random.Random(seed)

    def get_market_candidates(self, db: Session, league_id: int) -> List[Player]:
        """
        Returns players that are currently NOT owned by any manager (not in rosters),
        who can be offered on the market.
        """
        # Find player IDs in rosters
        rostered_ids = [r.player_id for r in db.query(Roster).filter(Roster.league_id == league_id).all()]

        # Get players not in rosters sorted by name for deterministic reproducible choice
        available_players = db.query(Player).filter(
            Player.league_id == league_id,
            ~Player.id.in_(rostered_ids) if rostered_ids else True
        ).order_by(Player.name, Player.club_name).all()

        return available_players

    def generate_daily_listings(self, db: Session, league_id: int, matchday_num: int, count: int = 15) -> List[Player]:
        """
        Generates the market listings for a matchday.
        Returns a list of `count` unowned players selected randomly (reproducibly) to be on the market.
        Creates a Market record.
        """
        # Create Market record if not exists
        market = db.query(Market).filter_by(league_id=league_id, matchday_number=matchday_num).first()
        if not market:
            market = Market(league_id=league_id, matchday_number=matchday_num, status="open")
            db.add(market)
            db.flush()

        candidates = self.get_market_candidates(db, league_id)
        if not candidates:
            return []

        # Select count players deterministically using self.rng
        selected = self.rng.sample(candidates, min(len(candidates), count))
        return selected

    def resolve_bids(self, db: Session, league_id: int, matchday_num: int) -> List[Transaction]:
        """
        Resolves all pending bids for the matchday.
        For each player, the highest bid wins.
        Winning manager's budget is deducted, player added to roster, and transaction created.
        All other bids are marked lost.
        """
        pending_bids = db.query(Bid).filter(
            Bid.league_id == league_id,
            Bid.matchday_number == matchday_num,
            Bid.status == "pending"
        ).all()

        if not pending_bids:
            return []

        # Group bids by player_id
        bids_by_player: Dict[int, List[Bid]] = {}
        for bid in pending_bids:
            bids_by_player.setdefault(bid.player_id, []).append(bid)

        transactions = []

        # Sort player keys to avoid hash iteration order changes based on auto-incrementing IDs
        for player_id in sorted(bids_by_player.keys()):
            bids = bids_by_player[player_id]
            # Sort bids by amount descending
            bids.sort(key=lambda b: b.amount, reverse=True)
            winning_bid = bids[0]

            # Double check manager's budget and player current ownership (roster)
            manager = db.query(Manager).filter_by(id=winning_bid.manager_id).first()
            player = db.query(Player).filter_by(id=player_id).first()

            is_already_rostered = db.query(Roster).filter_by(league_id=league_id, player_id=player_id).first() is not None

            if manager and player and not is_already_rostered and manager.budget >= winning_bid.amount:
                # Resolve winning bid
                winning_bid.status = "won"
                manager.budget -= winning_bid.amount

                # Add to roster
                roster_item = Roster(
                    league_id=league_id,
                    manager_id=manager.id,
                    player_id=player_id,
                    purchase_price=winning_bid.amount,
                    purchase_matchday=matchday_num
                )
                db.add(roster_item)

                # Record transaction
                tx = Transaction(
                    league_id=league_id,
                    manager_id=manager.id,
                    player_id=player_id,
                    type="BUY",
                    amount=winning_bid.amount,
                    matchday_number=matchday_num
                )
                db.add(tx)
                transactions.append(tx)

                # Mark other bids as lost
                for lost_bid in bids[1:]:
                    lost_bid.status = "lost"
            else:
                # Winning bid was invalid (e.g. manager overspent or player is already rostered)
                winning_bid.status = "lost"
                # If there are other bids, we don't cascade automatically in simple mode, just mark all lost
                for lost_bid in bids[1:]:
                    lost_bid.status = "lost"

        db.flush()
        return transactions

    def process_sales(self, db: Session, league_id: int, manager_id: int, player_id: int, sale_price: float, matchday_num: int) -> Optional[Transaction]:
        """
        Executes an instant sale of a player by a manager.
        The manager receives the sale_price, player is removed from roster, transaction recorded.
        """
        # Find roster item
        roster_item = db.query(Roster).filter_by(
            league_id=league_id,
            manager_id=manager_id,
            player_id=player_id
        ).first()

        if not roster_item:
            return None

        manager = db.query(Manager).filter_by(id=manager_id).first()
        if not manager:
            return None

        # Give budget
        manager.budget += sale_price

        # Remove from roster
        db.delete(roster_item)

        # Record transaction
        tx = Transaction(
            league_id=league_id,
            manager_id=manager_id,
            player_id=player_id,
            type="SELL",
            amount=sale_price,
            matchday_number=matchday_num
        )
        db.add(tx)
        db.flush()
        return tx

    def update_market_prices(self, db: Session, league_id: int, points_by_player: Dict[int, float]):
        """
        Adjust player market values based on their matchday points.
        High performance -> prices increase up to 10%
        Low/No performance -> prices drop down to 5%
        """
        # Sort players by name/club for absolute determinism in random generation sequence
        players = db.query(Player).filter(Player.league_id == league_id).order_by(Player.name, Player.club_name).all()
        for p in players:
            pts = points_by_player.get(p.id, 0.0)

            # Simple formula for price adjustment
            if pts >= 8.0:
                change = self.rng.uniform(0.05, 0.10)
            elif pts >= 4.0:
                change = self.rng.uniform(0.01, 0.04)
            elif pts <= 0.0:
                change = self.rng.uniform(-0.05, -0.02)
            else:
                change = self.rng.uniform(-0.01, 0.01)

            # Apply change and bound
            old_price = p.price
            new_price = old_price * (1.0 + change)
            p.price = round(max(200000.0, new_price), -4)
            p.market_value = p.price

        db.flush()
