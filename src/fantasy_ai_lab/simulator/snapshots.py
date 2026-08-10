import json
import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from src.fantasy_ai_lab.database.models import (
    League, Manager, Team, Player, Roster, Lineup, Transaction, Bid, Event,
    Decision, Situation, Snapshot
)

class SnapshotService:
    @staticmethod
    def create_snapshot(db: Session, league_id: int, matchday_num: int, description: Optional[str] = None) -> Snapshot:
        """
        Creates a JSON snapshot of the exact current state of a league.
        """
        league = db.query(League).filter_by(id=league_id).first()
        if not league:
            raise ValueError(f"League with ID {league_id} not found.")

        # Gather all related models
        managers = db.query(Manager).filter_by(league_id=league_id).all()
        teams = db.query(Team).filter_by(league_id=league_id).all()
        players = db.query(Player).filter_by(league_id=league_id).all()
        rosters = db.query(Roster).filter_by(league_id=league_id).all()
        lineups = db.query(Lineup).filter_by(league_id=league_id).all()
        transactions = db.query(Transaction).filter_by(league_id=league_id).all()
        bids = db.query(Bid).filter_by(league_id=league_id).all()
        events = db.query(Event).filter_by(league_id=league_id).all()
        decisions = db.query(Decision).filter_by(league_id=league_id).all()
        situations = db.query(Situation).filter_by(league_id=league_id).all()

        # Serialize
        data = {
            "league": {
                "name": league.name,
                "status": league.status,
                "matchday": league.matchday,
                "rules": league.rules,
                "seed": league.seed,
                "parent_league_id": league.parent_league_id
            },
            "managers": [
                {
                    "id": m.id,
                    "name": m.name,
                    "strategy_type": m.strategy_type,
                    "strategy_version": m.strategy_version,
                    "budget": m.budget,
                    "points": m.points,
                    "position": m.position
                } for m in managers
            ],
            "teams": [
                {
                    "name": t.name,
                    "external_team_id": t.external_team_id,
                    "level": t.level,
                    "strength": t.strength
                } for t in teams
            ],
            "players": [
                {
                    "id": p.id,
                    "name": p.name,
                    "position": p.position,
                    "club_name": p.club_name,
                    "price": p.price,
                    "market_value": p.market_value,
                    "xp": p.xp,
                    "form": p.form,
                    "play_probability": p.play_probability,
                    "status": p.status,
                    "status_duration": p.status_duration
                } for p in players
            ],
            "rosters": [
                {
                    "manager_id": r.manager_id,
                    "player_id": r.player_id,
                    "purchase_price": r.purchase_price,
                    "purchase_matchday": r.purchase_matchday
                } for r in rosters
            ],
            "lineups": [
                {
                    "manager_id": l.manager_id,
                    "matchday_number": l.matchday_number,
                    "formation": l.formation,
                    "goalkeeper_id": l.goalkeeper_id,
                    "defenders_ids": l.defenders_ids,
                    "midfielders_ids": l.midfielders_ids,
                    "forwards_ids": l.forwards_ids,
                    "substitutes_ids": l.substitutes_ids
                } for l in lineups
            ],
            "transactions": [
                {
                    "manager_id": t.manager_id,
                    "player_id": t.player_id,
                    "type": t.type,
                    "amount": t.amount,
                    "matchday_number": t.matchday_number
                } for t in transactions
            ],
            "bids": [
                {
                    "manager_id": b.manager_id,
                    "player_id": b.player_id,
                    "amount": b.amount,
                    "matchday_number": b.matchday_number,
                    "status": b.status
                } for b in bids
            ],
            "events": [
                {
                    "matchday_number": e.matchday_number,
                    "event_type": e.event_type,
                    "target_player_id": e.target_player_id,
                    "target_manager_id": e.target_manager_id,
                    "description": e.description,
                    "severity": e.severity,
                    "duration": e.duration,
                    "impact": e.impact,
                    "is_extreme": e.is_extreme
                } for e in events
            ],
            "decisions": [
                {
                    "manager_id": d.manager_id,
                    "player_id": d.player_id,
                    "matchday_number": d.matchday_number,
                    "action_type": d.action_type,
                    "amount": d.amount,
                    "confidence": d.confidence,
                    "strategy_version": d.strategy_version,
                    "reasoning_factors": d.reasoning_factors
                } for d in decisions
            ],
            "situations": [
                {
                    "manager_id": s.manager_id,
                    "player_id": s.player_id,
                    "matchday_number": s.matchday_number,
                    "state_features": s.state_features
                } for s in situations
            ]
        }

        # Save snapshot
        snapshot = Snapshot(
            league_id=league_id,
            matchday_number=matchday_num,
            snapshot_data=data,
            description=description or f"Snapshot League {league_id} Matchday {matchday_num}"
        )
        db.add(snapshot)
        db.commit()
        return snapshot

    @staticmethod
    def restore_snapshot(db: Session, snapshot_id: int) -> League:
        """
        Restores the state of the league from the snapshot.
        This wipes the current league state and replaces it.
        """
        snapshot = db.query(Snapshot).filter_by(id=snapshot_id).first()
        if not snapshot:
            raise ValueError(f"Snapshot with ID {snapshot_id} not found.")

        league_id = snapshot.league_id
        league = db.query(League).filter_by(id=league_id).first()
        if not league:
            raise ValueError(f"League with ID {league_id} not found.")

        data = snapshot.snapshot_data

        # 1. Wipe current league related tables
        db.query(Roster).filter_by(league_id=league_id).delete()
        db.query(Lineup).filter_by(league_id=league_id).delete()
        db.query(Transaction).filter_by(league_id=league_id).delete()
        db.query(Bid).filter_by(league_id=league_id).delete()
        db.query(Event).filter_by(league_id=league_id).delete()
        db.query(Decision).filter_by(league_id=league_id).delete()
        db.query(Situation).filter_by(league_id=league_id).delete()
        db.query(Player).filter_by(league_id=league_id).delete()
        db.query(Team).filter_by(league_id=league_id).delete()
        db.query(Manager).filter_by(league_id=league_id).delete()

        # 2. Restore League properties
        league_data = data["league"]
        league.name = league_data["name"]
        league.status = league_data["status"]
        league.matchday = league_data["matchday"]
        league.rules = league_data["rules"]
        league.seed = league_data["seed"]
        league.parent_league_id = league_data["parent_league_id"]

        # 3. Restore Managers (keeping track of mapping)
        manager_mapping = {}
        for m_data in data["managers"]:
            old_id = m_data["id"]
            mgr = Manager(
                league_id=league_id,
                name=m_data["name"],
                strategy_type=m_data["strategy_type"],
                strategy_version=m_data["strategy_version"],
                budget=m_data["budget"],
                points=m_data["points"],
                position=m_data["position"]
            )
            db.add(mgr)
            db.flush()
            manager_mapping[old_id] = mgr.id

        # 4. Restore Teams
        for t_data in data["teams"]:
            team = Team(
                league_id=league_id,
                name=t_data["name"],
                external_team_id=t_data["external_team_id"],
                level=t_data["level"],
                strength=t_data["strength"]
            )
            db.add(team)

        # 5. Restore Players (keeping track of mapping)
        player_mapping = {}
        for p_data in data["players"]:
            old_id = p_data["id"]
            player = Player(
                league_id=league_id,
                name=p_data["name"],
                position=p_data["position"],
                club_name=p_data["club_name"],
                price=p_data["price"],
                market_value=p_data["market_value"],
                xp=p_data["xp"],
                form=p_data["form"],
                play_probability=p_data["play_probability"],
                status=p_data["status"],
                status_duration=p_data["status_duration"]
            )
            db.add(player)
            db.flush()
            player_mapping[old_id] = player.id

        # 6. Restore Rosters
        for r_data in data["rosters"]:
            new_mgr_id = manager_mapping[r_data["manager_id"]]
            new_ply_id = player_mapping[r_data["player_id"]]
            roster = Roster(
                league_id=league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                purchase_price=r_data["purchase_price"],
                purchase_matchday=r_data["purchase_matchday"]
            )
            db.add(roster)

        # 7. Restore Lineups
        for l_data in data["lineups"]:
            new_mgr_id = manager_mapping[l_data["manager_id"]]
            lineup = Lineup(
                league_id=league_id,
                manager_id=new_mgr_id,
                matchday_number=l_data["matchday_number"],
                formation=l_data["formation"],
                goalkeeper_id=player_mapping.get(l_data["goalkeeper_id"]),
                defenders_ids=[player_mapping[old_id] for old_id in l_data["defenders_ids"] if old_id in player_mapping],
                midfielders_ids=[player_mapping[old_id] for old_id in l_data["midfielders_ids"] if old_id in player_mapping],
                forwards_ids=[player_mapping[old_id] for old_id in l_data["forwards_ids"] if old_id in player_mapping],
                substitutes_ids=[player_mapping[old_id] for old_id in l_data["substitutes_ids"] if old_id in player_mapping]
            )
            db.add(lineup)

        # 8. Restore Transactions
        for t_data in data["transactions"]:
            new_mgr_id = manager_mapping[t_data["manager_id"]]
            new_ply_id = player_mapping[t_data["player_id"]]
            tx = Transaction(
                league_id=league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                type=t_data["type"],
                amount=t_data["amount"],
                matchday_number=t_data["matchday_number"]
            )
            db.add(tx)

        # 9. Restore Bids
        for b_data in data["bids"]:
            new_mgr_id = manager_mapping[b_data["manager_id"]]
            new_ply_id = player_mapping[b_data["player_id"]]
            bid = Bid(
                league_id=league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                amount=b_data["amount"],
                matchday_number=b_data["matchday_number"],
                status=b_data["status"]
            )
            db.add(bid)

        # 10. Restore Events
        for e_data in data["events"]:
            evt = Event(
                league_id=league_id,
                matchday_number=e_data["matchday_number"],
                event_type=e_data["event_type"],
                target_player_id=player_mapping.get(e_data["target_player_id"]) if e_data.get("target_player_id") else None,
                target_manager_id=manager_mapping.get(e_data["target_manager_id"]) if e_data.get("target_manager_id") else None,
                description=e_data["description"],
                severity=e_data["severity"],
                duration=e_data["duration"],
                impact=e_data["impact"],
                is_extreme=e_data["is_extreme"]
            )
            db.add(evt)

        # 11. Restore Decisions & Situations
        for s_data in data["situations"]:
            new_mgr_id = manager_mapping[s_data["manager_id"]]
            new_ply_id = player_mapping.get(s_data["player_id"]) if s_data.get("player_id") else None
            sit = Situation(
                league_id=league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                matchday_number=s_data["matchday_number"],
                state_features=s_data["state_features"]
            )
            db.add(sit)

        for d_data in data["decisions"]:
            new_mgr_id = manager_mapping[d_data["manager_id"]]
            new_ply_id = player_mapping.get(d_data["player_id"]) if d_data.get("player_id") else None
            dec = Decision(
                league_id=league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                matchday_number=d_data["matchday_number"],
                action_type=d_data["action_type"],
                amount=d_data["amount"],
                confidence=d_data["confidence"],
                strategy_version=d_data["strategy_version"],
                reasoning_factors=d_data["reasoning_factors"]
            )
            db.add(dec)

        db.commit()
        return league

    @staticmethod
    def fork_snapshot(db: Session, snapshot_id: int, new_league_name: str) -> League:
        """
        Creates a new independent duplicate league based on the snapshot.
        The new league will have parent_league_id referencing the snapshot's league.
        """
        snapshot = db.query(Snapshot).filter_by(id=snapshot_id).first()
        if not snapshot:
            raise ValueError(f"Snapshot with ID {snapshot_id} not found.")

        data = snapshot.snapshot_data
        original_league_id = snapshot.league_id

        # 1. Create a brand new League
        league_data = data["league"]
        forked_league = League(
            simulation_id=None, # independent
            name=new_league_name,
            status=league_data["status"],
            matchday=league_data["matchday"],
            rules=league_data["rules"],
            seed=league_data["seed"] + 999, # offset seed to diversify behavior after fork
            parent_league_id=original_league_id
        )
        db.add(forked_league)
        db.flush()

        new_league_id = forked_league.id

        # 2. Restore Managers mapping to the new league ID
        manager_mapping = {}
        for m_data in data["managers"]:
            old_id = m_data["id"]
            mgr = Manager(
                league_id=new_league_id,
                name=m_data["name"],
                strategy_type=m_data["strategy_type"],
                strategy_version=m_data["strategy_version"],
                budget=m_data["budget"],
                points=m_data["points"],
                position=m_data["position"]
            )
            db.add(mgr)
            db.flush()
            manager_mapping[old_id] = mgr.id

        # 3. Restore Teams
        for t_data in data["teams"]:
            team = Team(
                league_id=new_league_id,
                name=t_data["name"],
                external_team_id=t_data["external_team_id"],
                level=t_data["level"],
                strength=t_data["strength"]
            )
            db.add(team)

        # 4. Restore Players mapping
        player_mapping = {}
        for p_data in data["players"]:
            old_id = p_data["id"]
            player = Player(
                league_id=new_league_id,
                name=p_data["name"],
                position=p_data["position"],
                club_name=p_data["club_name"],
                price=p_data["price"],
                market_value=p_data["market_value"],
                xp=p_data["xp"],
                form=p_data["form"],
                play_probability=p_data["play_probability"],
                status=p_data["status"],
                status_duration=p_data["status_duration"]
            )
            db.add(player)
            db.flush()
            player_mapping[old_id] = player.id

        # 5. Restore Rosters
        for r_data in data["rosters"]:
            new_mgr_id = manager_mapping[r_data["manager_id"]]
            new_ply_id = player_mapping[r_data["player_id"]]
            roster = Roster(
                league_id=new_league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                purchase_price=r_data["purchase_price"],
                purchase_matchday=r_data["purchase_matchday"]
            )
            db.add(roster)

        # 6. Restore Lineups
        for l_data in data["lineups"]:
            new_mgr_id = manager_mapping[l_data["manager_id"]]
            lineup = Lineup(
                league_id=new_league_id,
                manager_id=new_mgr_id,
                matchday_number=l_data["matchday_number"],
                formation=l_data["formation"],
                goalkeeper_id=player_mapping.get(l_data["goalkeeper_id"]),
                defenders_ids=[player_mapping[old_id] for old_id in l_data["defenders_ids"] if old_id in player_mapping],
                midfielders_ids=[player_mapping[old_id] for old_id in l_data["midfielders_ids"] if old_id in player_mapping],
                forwards_ids=[player_mapping[old_id] for old_id in l_data["forwards_ids"] if old_id in player_mapping],
                substitutes_ids=[player_mapping[old_id] for old_id in l_data["substitutes_ids"] if old_id in player_mapping]
            )
            db.add(lineup)

        # 7. Restore Transactions
        for t_data in data["transactions"]:
            new_mgr_id = manager_mapping[t_data["manager_id"]]
            new_ply_id = player_mapping[t_data["player_id"]]
            tx = Transaction(
                league_id=new_league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                type=t_data["type"],
                amount=t_data["amount"],
                matchday_number=t_data["matchday_number"]
            )
            db.add(tx)

        # 8. Restore Bids
        for b_data in data["bids"]:
            new_mgr_id = manager_mapping[b_data["manager_id"]]
            new_ply_id = player_mapping[b_data["player_id"]]
            bid = Bid(
                league_id=new_league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                amount=b_data["amount"],
                matchday_number=b_data["matchday_number"],
                status=b_data["status"]
            )
            db.add(bid)

        # 9. Restore Events
        for e_data in data["events"]:
            evt = Event(
                league_id=new_league_id,
                matchday_number=e_data["matchday_number"],
                event_type=e_data["event_type"],
                target_player_id=player_mapping.get(e_data["target_player_id"]) if e_data.get("target_player_id") else None,
                target_manager_id=manager_mapping.get(e_data["target_manager_id"]) if e_data.get("target_manager_id") else None,
                description=e_data["description"],
                severity=e_data["severity"],
                duration=e_data["duration"],
                impact=e_data["impact"],
                is_extreme=e_data["is_extreme"]
            )
            db.add(evt)

        # 10. Restore Decisions & Situations
        for s_data in data["situations"]:
            new_mgr_id = manager_mapping[s_data["manager_id"]]
            new_ply_id = player_mapping.get(s_data["player_id"]) if s_data.get("player_id") else None
            sit = Situation(
                league_id=new_league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                matchday_number=s_data["matchday_number"],
                state_features=s_data["state_features"]
            )
            db.add(sit)

        for d_data in data["decisions"]:
            new_mgr_id = manager_mapping[d_data["manager_id"]]
            new_ply_id = player_mapping.get(d_data["player_id"]) if d_data.get("player_id") else None
            dec = Decision(
                league_id=new_league_id,
                manager_id=new_mgr_id,
                player_id=new_ply_id,
                matchday_number=d_data["matchday_number"],
                action_type=d_data["action_type"],
                amount=d_data["amount"],
                confidence=d_data["confidence"],
                strategy_version=d_data["strategy_version"],
                reasoning_factors=d_data["reasoning_factors"]
            )
            db.add(dec)

        db.commit()
        return forked_league

    @staticmethod
    def replay_history(db: Session, league_id: int) -> List[Dict[str, Any]]:
        """
        Reconstructs step-by-step history of events, decisions and classification.
        """
        league = db.query(League).filter_by(id=league_id).first()
        if not league:
            raise ValueError(f"League {league_id} not found.")

        history = []

        # Query max matchday
        max_md = league.matchday
        for md in range(1, max_md + 1):
            events = db.query(Event).filter_by(league_id=league_id, matchday_number=md).all()
            decisions = db.query(Decision).filter_by(league_id=league_id, matchday_number=md).all()
            transactions = db.query(Transaction).filter_by(league_id=league_id, matchday_number=md).all()

            history.append({
                "matchday": md,
                "events_count": len(events),
                "events": [e.description for e in events],
                "decisions": [
                    {
                        "manager_id": d.manager_id,
                        "player_id": d.player_id,
                        "action": d.action_type,
                        "amount": d.amount,
                        "confidence": d.confidence
                    } for d in decisions
                ],
                "transactions": [
                    {
                        "manager_id": t.manager_id,
                        "player_id": t.player_id,
                        "type": t.type,
                        "amount": t.amount
                    } for t in transactions
                ]
            })

        return history
