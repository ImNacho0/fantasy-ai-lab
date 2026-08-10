import random
from typing import Dict, Any
from src.fantasy_ai_lab.database.models import Player

class ScoringEngine:
    def __init__(self, seed: int = 123):
        self.seed = seed
        self.rng = random.Random(seed)

    def calculate_player_points(self, player: Player) -> float:
        """
        Calculate points for a player in a matchday.
        Points are 0 if injured_grave or suspended.
        Otherwise, points are centered around (xP * form) * play_probability,
        with a random fluctuation depending on position.
        """
        if player.status in ["injured_grave", "suspended"]:
            return 0.0

        # Check if the player actually plays based on play_probability
        if self.rng.random() > player.play_probability:
            return 0.0

        # Status impact
        status_multiplier = 1.0
        if player.status == "injured_light":
            status_multiplier = 0.5  # underperforming or play fewer minutes
        elif player.status == "breakout":
            status_multiplier = 1.4  # stellar performance

        # Base expectation
        expected = player.xp * player.form * status_multiplier

        # Fluctuations depend on position (Forwards have higher variance, GKs have lower but stable)
        variance = {
            "GK": 1.5,
            "DF": 2.0,
            "MF": 2.5,
            "FW": 3.5
        }.get(player.position, 2.0)

        # Generate points following a normal distribution
        raw_points = self.rng.gauss(expected, variance)

        # Round and bound between -2.0 and 20.0 points
        points = round(max(-2.0, min(20.0, raw_points)), 1)
        return points
