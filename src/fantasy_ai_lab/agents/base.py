import random
from typing import List, Dict, Any, Optional
from src.fantasy_ai_lab.database.models import Manager, Player, Roster
from src.fantasy_ai_lab.strategy.base import get_strategy_by_name, BaseStrategy

class BaseAgent:
    def __init__(self, manager: Manager, seed: int = 123, strategy: Optional[BaseStrategy] = None):
        self.manager = manager
        self.seed = seed
        self.rng = random.Random(seed)

        # If strategy is passed directly, use it. Otherwise, look up by manager's strategy_type
        if strategy is not None:
            self.strategy = strategy
        else:
            # Safe fallback if strategy_type is empty or none
            strat_name = manager.strategy_type if manager.strategy_type else "Balanced"
            self.strategy = get_strategy_by_name(strat_name)

    def select_lineup(self, roster_players: List[Player]) -> Dict[str, Any]:
        """
        Delegates lineup selection to the configured Strategy.
        """
        return self.strategy.select_lineup(roster_players, self.rng)

    def make_market_decisions(self, market_players: List[Player], roster_players: List[Player]) -> List[Dict[str, Any]]:
        """
        Delegates market decisions to the configured Strategy.
        """
        return self.strategy.make_market_decisions(
            market_players=market_players,
            roster_players=roster_players,
            budget=self.manager.budget,
            rng=self.rng
        )
