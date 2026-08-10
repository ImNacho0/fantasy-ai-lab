import datetime
import json
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from src.fantasy_ai_lab.database.models import (
    League, Manager, Player, Roster, Lineup, Matchday, Market,
    Decision, Situation, Outcome, Reward, Event, Bid, Transaction
)
from src.fantasy_ai_lab.agents.base import BaseAgent
from src.fantasy_ai_lab.simulator.scoring import ScoringEngine
from src.fantasy_ai_lab.simulator.events import EventEngine
from src.fantasy_ai_lab.simulator.market import MarketEngine

class MatchdayEngine:
    def __init__(self, seed: int = 123):
        self.seed = seed
        self.scoring_engine = ScoringEngine(seed=seed)
        self.event_engine = EventEngine(seed=seed)
        self.market_engine = MarketEngine(seed=seed)

    def simulate_matchday(self, db: Session, league: League, matchday_num: int, extreme_scenario: str = None) -> Matchday:
        """
        Simulates a complete matchday for the given league.
        Saves all events, lineups, decisions, bids, resolutions, points, outcome and reward records.
        Marks matchday as completed.
        """
        # Create or fetch Matchday record
        matchday_record = db.query(Matchday).filter_by(
            league_id=league.id,
            matchday_number=matchday_num
        ).first()

        if not matchday_record:
            matchday_record = Matchday(
                league_id=league.id,
                matchday_number=matchday_num,
                status="pending"
            )
            db.add(matchday_record)
            db.flush()

        if matchday_record.status == "completed":
            return matchday_record # already simulated, skip for idempotency!

        # 1. Trigger Events (extreme scenarios or random events)
        events = []
        if extreme_scenario:
            events.extend(self.event_engine.trigger_scheduled_scenario(db, league.id, matchday_num, extreme_scenario))
        else:
            events.extend(self.event_engine.generate_random_events(db, league.id, matchday_num))

        # 2. Daily Market Listings
        market_listings = self.market_engine.generate_daily_listings(db, league.id, matchday_num)
        market_players_by_id = {p.id: p for p in market_listings}

        # 3. Manager/Agent Decisions
        # Sort managers by name to avoid dependency on database auto-incrementing ID
        managers = db.query(Manager).filter_by(league_id=league.id).order_by(Manager.name).all()
        decisions_made = []

        for idx, mgr in enumerate(managers):
            # Gather roster
            roster_items = db.query(Roster).filter_by(league_id=league.id, manager_id=mgr.id).all()
            # Order roster players by name to be stable
            roster_players = [db.query(Player).filter_by(id=r.player_id).first() for r in roster_items]
            roster_players = [p for p in roster_players if p is not None]
            roster_players.sort(key=lambda p: p.name)

            # Wrap in Agent (use relative index instead of mgr.id for reproducibility)
            agent_seed = self.seed + idx + matchday_num
            agent = BaseAgent(mgr, seed=agent_seed)

            # A. Select and Save Lineup
            lineup_dict = agent.select_lineup(roster_players)
            lineup_record = Lineup(
                league_id=league.id,
                manager_id=mgr.id,
                matchday_number=matchday_num,
                formation=lineup_dict["formation"],
                goalkeeper_id=lineup_dict["goalkeeper_id"],
                defenders_ids=lineup_dict["defenders_ids"],
                midfielders_ids=lineup_dict["midfielders_ids"],
                forwards_ids=lineup_dict["forwards_ids"],
                substitutes_ids=lineup_dict["substitutes_ids"]
            )
            db.add(lineup_record)
            db.flush()

            # Record Lineup Decision
            situation = Situation(
                league_id=league.id,
                manager_id=mgr.id,
                matchday_number=matchday_num,
                state_features={
                    "budget": mgr.budget,
                    "roster_count": len(roster_players),
                    "matchday": matchday_num,
                    "points": mgr.points
                }
            )
            db.add(situation)
            db.flush()

            dec = Decision(
                league_id=league.id,
                manager_id=mgr.id,
                matchday_number=matchday_num,
                action_type="LINEUP",
                confidence=1.0,
                strategy_version=mgr.strategy_version,
                reasoning_factors={"formation": lineup_dict["formation"]}
            )
            db.add(dec)
            db.flush()
            dec_dict = {"decision": dec, "situation": situation, "mgr": mgr, "type": "LINEUP", "roster_before": len(roster_players), "budget_before": mgr.budget}
            decisions_made.append(dec_dict)

            # B. Market Decisions (Buy/Sell)
            market_actions = agent.make_market_decisions(market_listings, roster_players)
            for action in market_actions:
                # Store Situation
                act_situation = Situation(
                    league_id=league.id,
                    manager_id=mgr.id,
                    player_id=action["player_id"],
                    matchday_number=matchday_num,
                    state_features={
                        "budget": mgr.budget,
                        "roster_count": len(roster_players),
                        "action_context": action["action"]
                    }
                )
                db.add(act_situation)
                db.flush()

                # Store Decision
                act_dec = Decision(
                    league_id=league.id,
                    manager_id=mgr.id,
                    player_id=action["player_id"],
                    matchday_number=matchday_num,
                    action_type=action["action"],
                    amount=action["amount"],
                    confidence=action["confidence"],
                    strategy_version=mgr.strategy_version,
                    reasoning_factors=action["reasoning"]
                )
                db.add(act_dec)
                db.flush()

                # Execute action or create bid
                if action["action"] == "SELL":
                    # Instant sale
                    self.market_engine.process_sales(
                        db=db,
                        league_id=league.id,
                        manager_id=mgr.id,
                        player_id=action["player_id"],
                        sale_price=action["amount"],
                        matchday_num=matchday_num
                    )
                elif action["action"] == "BUY":
                    # Place Bid
                    bid = Bid(
                        league_id=league.id,
                        manager_id=mgr.id,
                        player_id=action["player_id"],
                        amount=action["amount"],
                        matchday_number=matchday_num,
                        status="pending"
                    )
                    db.add(bid)
                    db.flush()

                dec_dict = {"decision": act_dec, "situation": act_situation, "mgr": mgr, "type": action["action"], "roster_before": len(roster_players), "budget_before": mgr.budget}
                decisions_made.append(dec_dict)

        # 4. Resolve all market Bids
        self.market_engine.resolve_bids(db, league.id, matchday_num)

        # 5. Simulate Points for Players in Active Lineups
        all_lineups = db.query(Lineup).filter_by(league_id=league.id, matchday_number=matchday_num).all()
        points_by_player: Dict[int, float] = {}

        # Collect all active player IDs in the lineup
        active_player_ids = set()
        for lineup in all_lineups:
            if lineup.goalkeeper_id:
                active_player_ids.add(lineup.goalkeeper_id)
            for p_id in (lineup.defenders_ids or []):
                active_player_ids.add(p_id)
            for p_id in (lineup.midfielders_ids or []):
                active_player_ids.add(p_id)
            for p_id in (lineup.forwards_ids or []):
                active_player_ids.add(p_id)

        # Calculate points for each active player in a stable, deterministic order by Name
        active_players = db.query(Player).filter(Player.id.in_(list(active_player_ids))).order_by(Player.name, Player.club_name).all() if active_player_ids else []
        for p_model in active_players:
            points_by_player[p_model.id] = self.scoring_engine.calculate_player_points(p_model)

        # 6. Calculate Manager Points & Update Rankings
        manager_pts_gained = {}
        for lineup in all_lineups:
            total_points = 0.0

            # Sum up points from active positions
            if lineup.goalkeeper_id:
                total_points += points_by_player.get(lineup.goalkeeper_id, 0.0)
            for p_id in (lineup.defenders_ids or []):
                total_points += points_by_player.get(p_id, 0.0)
            for p_id in (lineup.midfielders_ids or []):
                total_points += points_by_player.get(p_id, 0.0)
            for p_id in (lineup.forwards_ids or []):
                total_points += points_by_player.get(p_id, 0.0)

            # Round to 1 decimal place
            total_points = round(total_points, 1)

            # Add to manager
            mgr = db.query(Manager).filter_by(id=lineup.manager_id).first()
            if mgr:
                mgr.points += total_points
                manager_pts_gained[mgr.id] = total_points

        # Update manager classification positions
        sorted_managers = sorted(managers, key=lambda m: m.points, reverse=True)
        for rank, mgr in enumerate(sorted_managers, 1):
            mgr.position = rank

        # 7. Update market prices based on player performance
        self.market_engine.update_market_prices(db, league.id, points_by_player)

        # 8. Post-simulation Evaluation: Create Outcome and Reward records
        for item in decisions_made:
            dec = item["decision"]
            sit = item["situation"]
            mgr = item["mgr"]
            dec_type = item["type"]

            # Outcome metrics
            pts_gained = manager_pts_gained.get(mgr.id, 0.0) if dec_type == "LINEUP" else 0.0
            wealth_gained = mgr.budget - item["budget_before"] # change in budget cash

            out = Outcome(
                decision_id=dec.id,
                situation_id=sit.id,
                result_data={
                    "points_gained": pts_gained,
                    "wealth_change": wealth_gained,
                    "current_budget": mgr.budget
                },
                points_gained=pts_gained,
                wealth_gained=wealth_gained
            )
            db.add(out)
            db.flush()

            # Reward metric
            reward = Reward(
                decision_id=dec.id,
                points_score=pts_gained,
                wealth_score=wealth_gained / 1000000.0, # scaled wealth score
                risk_score=0.1 if dec_type == "BUY" else 0.0,
                total_reward=round(pts_gained + (wealth_gained / 1000000.0), 3),
                profile_name="balanced"
            )
            db.add(reward)

        # 9. Mark matchday as completed
        matchday_record.status = "completed"
        matchday_record.simulated_at = datetime.datetime.now(datetime.UTC).replace(tzinfo=None)

        # Advance league matchday counter
        league.matchday = matchday_num

        db.flush()
        return matchday_record
