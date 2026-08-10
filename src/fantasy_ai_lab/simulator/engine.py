import random
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from src.fantasy_ai_lab.database.models import (
    League, Manager, Team, Player, Roster, Simulation, Matchday, SimulationJob
)
from src.fantasy_ai_lab.data.provider import MockDataProvider
from src.fantasy_ai_lab.simulator.matchday import MatchdayEngine

class SimulationEngine:
    def __init__(self, seed: int = 123):
        self.seed = seed
        self.rng = random.Random(seed)

    def create_league(self, db: Session, name: str, seed: int, num_managers: int = 4, simulation_id: Optional[int] = None) -> League:
        """
        Creates a new league with teams, players, and managers initialized with starting rosters.
        """
        # Determine deterministic seeds from parent seed
        rng_local = random.Random(seed)
        data_seed = rng_local.randint(1, 1000000)

        # 1. Create League model
        league = League(
            simulation_id=simulation_id,
            name=name,
            status="active",
            matchday=0,
            seed=seed,
            rules={"starting_budget": 40000000.0, "roster_size_target": 15}
        )
        db.add(league)
        db.flush()

        # 2. Generate and store Teams and Players using DataProvider
        provider = MockDataProvider(seed=data_seed)
        teams_data = provider.get_teams()
        players_data = provider.get_players(teams_data)

        # Create teams in DB
        teams_models = []
        for t in teams_data:
            team_model = Team(
                league_id=league.id,
                name=t["name"],
                external_team_id=t["external_team_id"],
                level=t["level"],
                strength=t["strength"]
            )
            db.add(team_model)
            teams_models.append(team_model)
        db.flush()

        # Create players in DB
        players_models = []
        for p in players_data:
            player_model = Player(
                league_id=league.id,
                name=p["name"],
                position=p["position"],
                club_name=p["club_name"],
                price=p["price"],
                market_value=p["market_value"],
                xp=p["xp"],
                form=p["form"],
                play_probability=p["play_probability"],
                status=p["status"]
            )
            db.add(player_model)
            players_models.append(player_model)
        db.flush()

        # 3. Create Managers
        managers = []
        strategy_types = [
            "Balanced", "Conservative", "Aggressive", "Trader",
            "PointsMaximizer", "LongTerm", "Opportunistic", "BudgetManager", "Random"
        ]
        for i in range(num_managers):
            strat = strategy_types[i % len(strategy_types)]
            mgr = Manager(
                league_id=league.id,
                name=f"Manager {strat} {i+1}",
                strategy_type=strat,
                strategy_version="v1.0",
                budget=40000000.0,
                points=0.0,
                position=1
            )
            db.add(mgr)
            managers.append(mgr)
        db.flush()

        # 4. Draft Initial Rosters for each manager (deterministically)
        # To avoid managers drawing from empty pools, we distribute a basic squad of 15 players per manager:
        # 1 GK, 5 DF, 5 MF, 4 FW.
        # This will be subtracted from their 40M budget.
        all_players = list(players_models)
        rng_local.shuffle(all_players)

        for mgr in managers:
            gks = [p for p in all_players if p.position == "GK"]
            dfs = [p for p in all_players if p.position == "DF"]
            mfs = [p for p in all_players if p.position == "MF"]
            fws = [p for p in all_players if p.position == "FW"]

            selected_players = []
            selected_players.append(gks[0])
            selected_players.extend(dfs[:5])
            selected_players.extend(mfs[:5])
            selected_players.extend(fws[:4])

            # Deduct from budget and save roster
            for p in selected_players:
                # Add to roster
                roster_item = Roster(
                    league_id=league.id,
                    manager_id=mgr.id,
                    player_id=p.id,
                    purchase_price=p.price,
                    purchase_matchday=0
                )
                db.add(roster_item)

                # Deduct price from budget
                mgr.budget -= p.price

                # Remove from draft pool
                all_players.remove(p)

        db.flush()
        return league

    def run_league_simulation(self, db: Session, league_id: int, matchdays_total: int, extreme_scenarios: Optional[Dict[int, str]] = None) -> League:
        """
        Runs the simulation of matchdays for a league.
        """
        league = db.query(League).filter_by(id=league_id).first()
        if not league:
            raise ValueError(f"League with ID {league_id} not found.")

        current_md = league.matchday

        # Initialize matchday engine with seed derived from league seed
        md_engine = MatchdayEngine(seed=league.seed)

        for md in range(current_md + 1, matchdays_total + 1):
            # Check for extreme scenario in this matchday
            scenario = extreme_scenarios.get(md) if extreme_scenarios else None

            # Simulate matchday
            md_engine.simulate_matchday(db, league, md, extreme_scenario=scenario)

            # Complete the transaction block per matchday
            db.commit()

        # Mark league completed
        if league.matchday >= matchdays_total:
            league.status = "completed"
            db.commit()

        return league
