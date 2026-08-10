import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Tuple
from pydantic import BaseModel, ConfigDict, Field

class StrategyConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str
    risk_tolerance: float = Field(0.5, ge=0.0, le=1.0, alias="riskTolerance")
    points_weight: float = Field(0.5, ge=0.0, le=1.0, alias="pointsWeight")
    value_growth_weight: float = Field(0.5, ge=0.0, le=1.0, alias="valueGrowthWeight")
    cash_weight: float = Field(0.5, ge=0.0, le=1.0, alias="cashWeight")
    future_weight: float = Field(0.5, ge=0.0, le=1.0, alias="futureWeight")
    market_weight: float = Field(0.5, ge=0.0, le=1.0, alias="marketWeight")
    injury_risk_weight: float = Field(0.5, ge=0.0, le=1.0, alias="injuryRiskWeight")


class BaseStrategy(ABC):
    def __init__(self, config: StrategyConfig):
        self.config = config

    @abstractmethod
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        """
        Selects active lineup of 11 players from the manager's roster.
        """
        pass

    @abstractmethod
    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        """
        Returns list of decisions: BUY, SELL, HOLD.
        """
        pass


class ConservativeStrategy(BaseStrategy):
    """
    Conservative Strategy: Prioritizes low-risk, stability, and high liquidity.
    Avoids injured players and places low, safe bids.
    """
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        # Filter out injured players
        available = [p for p in roster_players if p.status not in ["injured_grave", "injured_light"]]
        fallback = [p for p in roster_players if p not in available]
        candidates = available + fallback

        gks = [p for p in candidates if p.position == "GK"]
        dfs = [p for p in candidates if p.position == "DF"]
        mfs = [p for p in candidates if p.position == "MF"]
        fws = [p for p in candidates if p.position == "FW"]

        # Basic 4-4-2 formation
        selected_gk = gks[:1]
        selected_df = dfs[:4]
        selected_mf = mfs[:4]
        selected_fw = fws[:2]

        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        decisions = []

        # 1. Sell injured players to avoid losses
        for p in roster_players:
            if p.status in ["injured_grave", "injured_light"]:
                decisions.append({
                    "action": "SELL",
                    "player_id": p.id,
                    "amount": round(p.market_value * 0.95, -4),
                    "confidence": 0.9,
                    "reasoning": {"reason": "risk_aversion_injured", "status": p.status}
                })

        # 2. Buy only if budget is very healthy (>10M) and we have space
        if budget > 10000000 and len(roster_players) < 16:
            healthy_market = [p for p in market_players if p.status == "healthy"]
            # Sort by expected points / price ratio (value for money)
            best_value = sorted(healthy_market, key=lambda p: p.xp / max(1.0, p.price), reverse=True)
            for p in best_value:
                if budget >= p.price:
                    # Low conservative bid
                    bid_multiplier = rng.uniform(1.01, 1.04)
                    bid_amount = round(p.price * bid_multiplier, -4)
                    if bid_amount <= budget:
                        decisions.append({
                            "action": "BUY",
                            "player_id": p.id,
                            "amount": bid_amount,
                            "confidence": 0.8,
                            "reasoning": {"reason": "conservative_value_bid", "multiplier": round(bid_multiplier, 3)}
                        })
                        break
        return decisions


class AggressiveStrategy(BaseStrategy):
    """
    Aggressive Strategy: Focuses on high-reward opportunities and growth.
    Bids highly to secure stars and tolerates injury risk.
    """
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        # Sort candidates by xP * form (highest immediate points potential)
        candidates = sorted(roster_players, key=lambda p: p.xp * p.form, reverse=True)

        gks = [p for p in candidates if p.position == "GK"]
        dfs = [p for p in candidates if p.position == "DF"]
        mfs = [p for p in candidates if p.position == "MF"]
        fws = [p for p in candidates if p.position == "FW"]

        selected_gk = gks[:1]
        selected_df = dfs[:4]
        selected_mf = mfs[:4]
        selected_fw = fws[:2]

        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        decisions = []

        # Aggressive doesn't sell easily unless extremely necessary
        for p in roster_players:
            if p.status == "injured_grave" and len(roster_players) > 15:
                decisions.append({
                    "action": "SELL",
                    "player_id": p.id,
                    "amount": round(p.market_value * 0.90, -4),
                    "confidence": 0.6,
                    "reasoning": {"reason": "aggressive_liquidate_grave", "status": p.status}
                })

        # Buy high xP stars, willing to bid heavily
        if budget > 2000000 and len(roster_players) < 18:
            stars = sorted(market_players, key=lambda p: p.xp, reverse=True)
            for p in stars:
                if budget >= p.price:
                    # High aggressive bid to secure the player
                    bid_multiplier = rng.uniform(1.10, 1.25)
                    bid_amount = round(p.price * bid_multiplier, -4)
                    if bid_amount <= budget:
                        decisions.append({
                            "action": "BUY",
                            "player_id": p.id,
                            "amount": bid_amount,
                            "confidence": 0.9,
                            "reasoning": {"reason": "aggressive_star_bid", "multiplier": round(bid_multiplier, 3)}
                        })
                        break
        return decisions


class TraderStrategy(BaseStrategy):
    """
    Trader Strategy: Prioritizes value growth and buy/sell operations.
    Purchases undervalued players and sells when prices rise.
    """
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        # General lineup (standard 4-4-2)
        gks = [p for p in roster_players if p.position == "GK"]
        dfs = [p for p in roster_players if p.position == "DF"]
        mfs = [p for p in roster_players if p.position == "MF"]
        fws = [p for p in roster_players if p.position == "FW"]

        selected_gk = gks[:1]
        selected_df = dfs[:4]
        selected_mf = mfs[:4]
        selected_fw = fws[:2]

        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        decisions = []

        # Sell players who are on breakout (high price) or whose market value > price
        for p in roster_players:
            if p.status == "breakout":
                decisions.append({
                    "action": "SELL",
                    "player_id": p.id,
                    "amount": round(p.market_value * 1.05, -4),
                    "confidence": 0.85,
                    "reasoning": {"reason": "trader_profit_take", "status": p.status}
                })
            elif p.status == "injured_grave":
                decisions.append({
                    "action": "SELL",
                    "player_id": p.id,
                    "amount": round(p.market_value * 0.90, -4),
                    "confidence": 0.8,
                    "reasoning": {"reason": "trader_cut_losses", "status": p.status}
                })

        # Buy undervalued/growing players
        if budget > 1000000 and len(roster_players) < 18:
            # Sort by potential form or xP/price ratio
            undervalued = sorted(market_players, key=lambda p: p.market_value / max(1.0, p.price), reverse=True)
            for p in undervalued:
                if budget >= p.price:
                    bid_multiplier = rng.uniform(1.02, 1.08)
                    bid_amount = round(p.price * bid_multiplier, -4)
                    if bid_amount <= budget:
                        decisions.append({
                            "action": "BUY",
                            "player_id": p.id,
                            "amount": bid_amount,
                            "confidence": 0.75,
                            "reasoning": {"reason": "trader_undervalued_buy", "multiplier": round(bid_multiplier, 3)}
                        })
                        break
        return decisions


class PointsMaximizerStrategy(BaseStrategy):
    """
    Points Maximizer Strategy: Prioritizes immediate points, lineup quality, and xP.
    """
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        # Strongly sort roster by immediate expected points (xp * form)
        candidates = sorted(roster_players, key=lambda p: p.xp * p.form, reverse=True)

        gks = [p for p in candidates if p.position == "GK"]
        dfs = [p for p in candidates if p.position == "DF"]
        mfs = [p for p in candidates if p.position == "MF"]
        fws = [p for p in candidates if p.position == "FW"]

        selected_gk = gks[:1]
        selected_df = dfs[:4]
        selected_mf = mfs[:4]
        selected_fw = fws[:2]

        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        decisions = []

        # Sell players who have low points expectation
        if len(roster_players) > 14:
            worst_players = sorted(roster_players, key=lambda p: p.xp * p.form)
            worst = worst_players[0]
            if worst.status == "injured_grave":
                decisions.append({
                    "action": "SELL",
                    "player_id": worst.id,
                    "amount": round(worst.market_value * 0.90, -4),
                    "confidence": 0.85,
                    "reasoning": {"reason": "points_max_liquidate_lowest_xp", "xp": worst.xp}
                })

        # Buy highest xP players on market
        if budget > 2000000 and len(roster_players) < 18:
            high_xp = sorted(market_players, key=lambda p: p.xp * p.form, reverse=True)
            for p in high_xp:
                if budget >= p.price:
                    bid_multiplier = rng.uniform(1.05, 1.15)
                    bid_amount = round(p.price * bid_multiplier, -4)
                    if bid_amount <= budget:
                        decisions.append({
                            "action": "BUY",
                            "player_id": p.id,
                            "amount": bid_amount,
                            "confidence": 0.85,
                            "reasoning": {"reason": "points_max_high_xp_bid", "multiplier": round(bid_multiplier, 3)}
                        })
                        break
        return decisions


class LongTermStrategy(BaseStrategy):
    """
    Long Term Strategy: Prioritizes base xP and stability across multiple matchdays.
    Tolerates short-term injury if long-term potential is high.
    """
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        # Sort by base xP (long-term projection)
        candidates = sorted(roster_players, key=lambda p: p.xp, reverse=True)

        gks = [p for p in candidates if p.position == "GK"]
        dfs = [p for p in candidates if p.position == "DF"]
        mfs = [p for p in candidates if p.position == "MF"]
        fws = [p for p in candidates if p.position == "FW"]

        selected_gk = gks[:1]
        selected_df = dfs[:4]
        selected_mf = mfs[:4]
        selected_fw = fws[:2]

        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        decisions = []
        # Holds long-term injured if they are highly rated
        for p in roster_players:
            if p.status == "injured_grave" and p.xp < 3.0:
                decisions.append({
                    "action": "SELL",
                    "player_id": p.id,
                    "amount": round(p.market_value * 0.90, -4),
                    "confidence": 0.8,
                    "reasoning": {"reason": "long_term_liquidate_low_xp_injured"}
                })

        # Buy high base-xp players
        if budget > 2000000 and len(roster_players) < 18:
            high_base_xp = sorted(market_players, key=lambda p: p.xp, reverse=True)
            for p in high_base_xp:
                if budget >= p.price:
                    bid_multiplier = rng.uniform(1.02, 1.10)
                    bid_amount = round(p.price * bid_multiplier, -4)
                    if bid_amount <= budget:
                        decisions.append({
                            "action": "BUY",
                            "player_id": p.id,
                            "amount": bid_amount,
                            "confidence": 0.8,
                            "reasoning": {"reason": "long_term_quality_investment", "multiplier": round(bid_multiplier, 3)}
                        })
                        break
        return decisions


class OpportunisticStrategy(BaseStrategy):
    """
    Opportunistic Strategy: Searches for extreme market value discounts or bargain rates.
    """
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        # Standard lineup
        gks = [p for p in roster_players if p.position == "GK"]
        dfs = [p for p in roster_players if p.position == "DF"]
        mfs = [p for p in roster_players if p.position == "MF"]
        fws = [p for p in roster_players if p.position == "FW"]

        selected_gk = gks[:1]
        selected_df = dfs[:4]
        selected_mf = mfs[:4]
        selected_fw = fws[:2]

        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        decisions = []

        # Sell if value is significantly higher than purchase price (profit take)
        for p in roster_players:
            if p.status == "breakout":
                decisions.append({
                    "action": "SELL",
                    "player_id": p.id,
                    "amount": round(p.market_value * 1.05, -4),
                    "confidence": 0.8,
                    "reasoning": {"reason": "opportunistic_profit_take"}
                })

        # Buy absolute bargain players (market_value / price ratio > 1.1)
        if budget > 1000000 and len(roster_players) < 18:
            bargains = [p for p in market_players if p.market_value >= p.price * 1.05]
            if bargains:
                best_bargain = sorted(bargains, key=lambda p: p.market_value / p.price, reverse=True)[0]
                if budget >= best_bargain.price:
                    bid_multiplier = rng.uniform(1.01, 1.05)
                    bid_amount = round(best_bargain.price * bid_multiplier, -4)
                    if bid_amount <= budget:
                        decisions.append({
                            "action": "BUY",
                            "player_id": best_bargain.id,
                            "amount": bid_amount,
                            "confidence": 0.85,
                            "reasoning": {"reason": "opportunistic_bargain_buy", "multiplier": round(bid_multiplier, 3)}
                        })
        return decisions


class BudgetManagerStrategy(BaseStrategy):
    """
    Budget Manager Strategy: Extremely strict with cash and liquidity.
    """
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        # Standard lineup
        gks = [p for p in roster_players if p.position == "GK"]
        dfs = [p for p in roster_players if p.position == "DF"]
        mfs = [p for p in roster_players if p.position == "MF"]
        fws = [p for p in roster_players if p.position == "FW"]

        selected_gk = gks[:1]
        selected_df = dfs[:4]
        selected_mf = mfs[:4]
        selected_fw = fws[:2]

        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        decisions = []

        # If budget is critically low, liquidate expensive players
        if budget < 5000000 and len(roster_players) > 12:
            expensive_player = sorted(roster_players, key=lambda p: p.price, reverse=True)[0]
            decisions.append({
                "action": "SELL",
                "player_id": expensive_player.id,
                "amount": round(expensive_player.market_value * 0.95, -4),
                "confidence": 0.9,
                "reasoning": {"reason": "budget_liquidity_recovery"}
            })

        # Buy only extremely cheap players (price < 3M)
        if budget > 15000000 and len(roster_players) < 15:
            cheap_players = [p for p in market_players if p.price < 3000000]
            if cheap_players:
                best_cheap = sorted(cheap_players, key=lambda p: p.xp, reverse=True)[0]
                if budget >= best_cheap.price:
                    bid_multiplier = rng.uniform(1.01, 1.03)
                    bid_amount = round(best_cheap.price * bid_multiplier, -4)
                    if bid_amount <= budget:
                        decisions.append({
                            "action": "BUY",
                            "player_id": best_cheap.id,
                            "amount": bid_amount,
                            "confidence": 0.8,
                            "reasoning": {"reason": "budget_cheap_fill_buy", "multiplier": round(bid_multiplier, 3)}
                        })
        return decisions


class BalancedStrategy(BaseStrategy):
    """
    Balanced Strategy: Combines points, value, risk, and liquidity.
    """
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        # Weighted lineup selection
        candidates = sorted(roster_players, key=lambda p: p.xp * p.form * p.play_probability, reverse=True)

        gks = [p for p in candidates if p.position == "GK"]
        dfs = [p for p in candidates if p.position == "DF"]
        mfs = [p for p in candidates if p.position == "MF"]
        fws = [p for p in candidates if p.position == "FW"]

        selected_gk = gks[:1]
        selected_df = dfs[:4]
        selected_mf = mfs[:4]
        selected_fw = fws[:2]

        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        decisions = []

        # Standard balanced sells
        for p in roster_players:
            if p.status == "injured_grave":
                decisions.append({
                    "action": "SELL",
                    "player_id": p.id,
                    "amount": round(p.market_value * 0.90, -4),
                    "confidence": 0.8,
                    "reasoning": {"reason": "balanced_liquidate_grave"}
                })

        # Standard balanced buy
        if budget > 3000000 and len(roster_players) < 16:
            candidates = sorted(market_players, key=lambda p: p.xp * p.form, reverse=True)
            for p in candidates:
                if budget >= p.price:
                    bid_multiplier = rng.uniform(1.03, 1.10)
                    bid_amount = round(p.price * bid_multiplier, -4)
                    if bid_amount <= budget:
                        decisions.append({
                            "action": "BUY",
                            "player_id": p.id,
                            "amount": bid_amount,
                            "confidence": 0.75,
                            "reasoning": {"reason": "balanced_bid", "multiplier": round(bid_multiplier, 3)}
                        })
                        break
        return decisions


class RandomBaselineStrategy(BaseStrategy):
    """
    Random Baseline Strategy: Simulates a base agent acting pseudo-randomly.
    """
    def select_lineup(self, roster_players: List[Any], rng: random.Random) -> Dict[str, Any]:
        # Shuffle candidates
        shuffled = list(roster_players)
        rng.shuffle(shuffled)

        gks = [p for p in shuffled if p.position == "GK"]
        dfs = [p for p in shuffled if p.position == "DF"]
        mfs = [p for p in shuffled if p.position == "MF"]
        fws = [p for p in shuffled if p.position == "FW"]

        selected_gk = gks[:1]
        selected_df = dfs[:4]
        selected_mf = mfs[:4]
        selected_fw = fws[:2]

        selected_ids = {p.id for p in selected_gk + selected_df + selected_mf + selected_fw}
        substitutes = [p for p in roster_players if p.id not in selected_ids]

        return {
            "formation": "4-4-2",
            "goalkeeper_id": selected_gk[0].id if selected_gk else None,
            "defenders_ids": [p.id for p in selected_df],
            "midfielders_ids": [p.id for p in selected_mf],
            "forwards_ids": [p.id for p in selected_fw],
            "substitutes_ids": [p.id for p in substitutes]
        }

    def make_market_decisions(
        self,
        market_players: List[Any],
        roster_players: List[Any],
        budget: float,
        rng: random.Random
    ) -> List[Dict[str, Any]]:
        decisions = []

        # 1. Random sell
        if len(roster_players) > 13 and rng.random() < 0.15:
            target = rng.choice(roster_players)
            decisions.append({
                "action": "SELL",
                "player_id": target.id,
                "amount": round(target.market_value * rng.uniform(0.9, 1.0), -4),
                "confidence": rng.uniform(0.3, 0.7),
                "reasoning": {"reason": "random_baseline_sell"}
            })

        # 2. Random buy
        if budget > 1000000 and len(roster_players) < 18 and rng.random() < 0.3 and market_players:
            p = rng.choice(market_players)
            if budget >= p.price:
                bid_multiplier = rng.uniform(1.0, 1.15)
                bid_amount = round(p.price * bid_multiplier, -4)
                if bid_amount <= budget:
                    decisions.append({
                        "action": "BUY",
                        "player_id": p.id,
                        "amount": bid_amount,
                        "confidence": rng.uniform(0.4, 0.8),
                        "reasoning": {"reason": "random_baseline_buy", "multiplier": round(bid_multiplier, 3)}
                    })
        return decisions


def get_strategy_by_name(name: str, parameters: Dict[str, Any] = None) -> BaseStrategy:
    configs = {
        "Conservative": StrategyConfig(name="Conservative", risk_tolerance=0.1, points_weight=0.3, value_growth_weight=0.3, cash_weight=0.9, future_weight=0.3, market_weight=0.2, injury_risk_weight=0.9),
        "Aggressive": StrategyConfig(name="Aggressive", risk_tolerance=0.9, points_weight=0.9, value_growth_weight=0.7, cash_weight=0.1, future_weight=0.8, market_weight=0.8, injury_risk_weight=0.1),
        "Trader": StrategyConfig(name="Trader", risk_tolerance=0.6, points_weight=0.2, value_growth_weight=0.9, cash_weight=0.6, future_weight=0.5, market_weight=0.9, injury_risk_weight=0.4),
        "PointsMaximizer": StrategyConfig(name="PointsMaximizer", risk_tolerance=0.7, points_weight=1.0, value_growth_weight=0.3, cash_weight=0.2, future_weight=0.4, market_weight=0.6, injury_risk_weight=0.3),
        "LongTerm": StrategyConfig(name="LongTerm", risk_tolerance=0.4, points_weight=0.6, value_growth_weight=0.6, cash_weight=0.3, future_weight=1.0, market_weight=0.5, injury_risk_weight=0.5),
        "Opportunistic": StrategyConfig(name="Opportunistic", risk_tolerance=0.5, points_weight=0.4, value_growth_weight=0.8, cash_weight=0.5, future_weight=0.6, market_weight=1.0, injury_risk_weight=0.4),
        "BudgetManager": StrategyConfig(name="BudgetManager", risk_tolerance=0.2, points_weight=0.3, value_growth_weight=0.4, cash_weight=1.0, future_weight=0.3, market_weight=0.3, injury_risk_weight=0.6),
        "Balanced": StrategyConfig(name="Balanced", risk_tolerance=0.5, points_weight=0.6, value_growth_weight=0.5, cash_weight=0.5, future_weight=0.6, market_weight=0.6, injury_risk_weight=0.5),
        "Random": StrategyConfig(name="Random", risk_tolerance=0.5, points_weight=0.5, value_growth_weight=0.5, cash_weight=0.5, future_weight=0.5, market_weight=0.5, injury_risk_weight=0.5),
    }

    # Mapping name aliases
    name_mapped = name
    if "Budget" in name_mapped:
        name_mapped = "BudgetManager"
    elif "Points" in name_mapped:
        name_mapped = "PointsMaximizer"

    config = configs.get(name_mapped, configs["Balanced"])
    if parameters:
        # Accept both persisted snake_case and API-friendly camelCase keys.
        config = config.model_copy(update=parameters)

    strategies = {
        "Conservative": ConservativeStrategy,
        "Aggressive": AggressiveStrategy,
        "Trader": TraderStrategy,
        "PointsMaximizer": PointsMaximizerStrategy,
        "LongTerm": LongTermStrategy,
        "Opportunistic": OpportunisticStrategy,
        "BudgetManager": BudgetManagerStrategy,
        "Balanced": BalancedStrategy,
        "Random": RandomBaselineStrategy,
    }

    strategy_cls = strategies.get(name_mapped, BalancedStrategy)
    return strategy_cls(config)
