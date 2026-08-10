"""Read-only boundary for connecting fantasy-manager to the lab.

The adapter accepts a plain snapshot so the simulator never depends on the
external application's transport, ORM, or execution API. It intentionally
returns decisions only; execution remains the responsibility of fantasy-manager.
"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.orm import Session

from fantasy_ai_lab.knowledge.memory import KnowledgeService


class FantasyManagerAdapter:
    MODE = "read-only"

    @staticmethod
    def _features(snapshot: Dict[str, Any]) -> Dict[str, Any]:
        league_state = snapshot.get("leagueState") or snapshot.get("league_state") or {}
        team = snapshot.get("team") or {}
        context = snapshot.get("context") or {}
        market = snapshot.get("market") or {}
        player = context.get("player") or {}
        features = {
            "playerPrice": player.get("price", context.get("playerPrice", 0.0)),
            "playerStatus": player.get("status", context.get("playerStatus", "unknown")),
            "playerPosition": player.get("position", context.get("playerPosition", "unknown")),
            "budget": team.get("budget", 0.0),
            "roster_count": len(team.get("roster", [])) if isinstance(team.get("roster"), list) else team.get("roster_count", 0),
            "matchday": league_state.get("matchday", 0),
            "marketActivity": market.get("activity", market.get("liquidity", "unknown")),
            "action_context": context.get("action", "HOLD"),
        }
        return {key: value for key, value in features.items() if value is not None}

    @staticmethod
    def recommend(db: Session, snapshot: Dict[str, Any], limit: int = 10) -> Dict[str, Any]:
        features = FantasyManagerAdapter._features(snapshot)
        evidence = KnowledgeService.recommend(db, features, limit=limit)
        winner = evidence["ranking"][0] if evidence["ranking"] else None
        action = winner["action"] if winner else "HOLD"
        confidence = float(winner["decision_confidence"]) if winner else 0.0
        player = (snapshot.get("context") or {}).get("player") or {}
        player_id = player.get("id", (snapshot.get("context") or {}).get("playerId"))
        price = float(player.get("price", (snapshot.get("context") or {}).get("playerPrice", 0.0)) or 0.0)
        return {
            "mode": FantasyManagerAdapter.MODE,
            "recommendedAction": action,
            "playerId": player_id,
            "amount": round(price * 1.05, -4) if action == "BUY" and price else None,
            "confidence": confidence,
            "expectedOutcome": winner or {},
            "similarCases": evidence["cases"],
            "sampleSize": evidence["sample_size"],
            "outcomeSampleSize": evidence["outcome_sample_size"],
            "historicalMemory": evidence,
            "strategyVersion": (winner or {}).get("strategy_version"),
            "execution": {"allowed": False, "owner": "fantasy-manager"},
            "features": features,
        }
