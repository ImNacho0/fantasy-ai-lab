import random
from typing import List, Dict, Any, Optional
from src.fantasy_ai_lab.database.models import Manager, Player, Roster

class BaseAgent:
    def __init__(self, manager: Manager, seed: int = 123):
        self.manager = manager
        self.seed = seed
        self.rng = random.Random(seed)

    def select_lineup(self, roster_players: List[Player]) -> Dict[str, Any]:
        """
        Selects a valid lineup of 11 players from the roster.
        Returns a dictionary with formation, goalkeeper_id, defenders_ids, midfielders_ids, forwards_ids, and substitutes_ids.
        Supported formation in Fase 1: 4-4-2 (or dynamically adapted based on roster).
        If roster has fewer than 11 players, select as many as possible.
        """
        # Group roster players by position
        gks = [p for p in roster_players if p.position == "GK" and p.status != "injured_grave"]
        dfs = [p for p in roster_players if p.position == "DF" and p.status != "injured_grave"]
        mfs = [p for p in roster_players if p.position == "MF" and p.status != "injured_grave"]
        fws = [p for p in roster_players if p.position == "FW" and p.status != "injured_grave"]

        # Basic 4-4-2 formation requirement
        req_gk, req_df, req_mf, req_fw = 1, 4, 4, 2

        selected_gk = gks[:req_gk]
        selected_df = dfs[:req_df]
        selected_mf = mfs[:req_mf]
        selected_fw = fws[:req_fw]

        # Collect leftover players as substitutes
        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids and p.status != "injured_grave"]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(self, market_players: List[Player], roster_players: List[Player]) -> List[Dict[str, Any]]:
        """
        Generates buy, sell, or hold decisions.
        Returns a list of dicts:
        [ { "action": "BUY"|"SELL"|"HOLD", "player_id": int, "amount": float, "confidence": float, "reasoning": dict } ]
        """
        decisions = []

        # 1. Decide on selling (e.g. if we have too many players or an injured player or randomly)
        # Conservative/Trader style would sell injured_grave players. Let's do that!
        for p in roster_players:
            if p.status == "injured_grave":
                # Sell injured player for 90% of market value to free budget
                decisions.append({
                    "action": "SELL",
                    "player_id": p.id,
                    "amount": round(p.market_value * 0.9, -4),
                    "confidence": 0.8,
                    "reasoning": {"reason": "player_injured_grave", "status": p.status}
                })
            elif self.rng.random() < 0.1 and len(roster_players) > 12:
                # Randomly sell a player occasionally to recycle roster
                decisions.append({
                    "action": "SELL",
                    "player_id": p.id,
                    "amount": round(p.market_value * self.rng.uniform(0.95, 1.05), -4),
                    "confidence": 0.5,
                    "reasoning": {"reason": "random_roster_recycle"}
                })

        # 2. Decide on buying from the market
        # Simple bidding behavior: if budget > 5M and roster size < 15, let's bid on a high-xP player
        budget = self.manager.budget
        if budget > 2000000 and len(roster_players) < 18:
            # Sort market players by xP
            sorted_market = sorted(market_players, key=lambda p: p.xp * p.form, reverse=True)
            for p in sorted_market:
                # Can we afford the base price?
                if budget >= p.price:
                    # Bid slightly above price depending on personality
                    bid_multiplier = self.rng.uniform(1.01, 1.15)
                    bid_amount = round(p.price * bid_multiplier, -4)
                    if bid_amount <= budget:
                        decisions.append({
                            "action": "BUY",
                            "player_id": p.id,
                            "amount": bid_amount,
                            "confidence": 0.7,
                            "reasoning": {"reason": "high_xp_bid", "multiplier": round(bid_multiplier, 3)}
                        })
                        break # Only place one buy bid per matchday in simple mode

        return decisions
