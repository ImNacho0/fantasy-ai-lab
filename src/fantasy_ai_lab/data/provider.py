import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any

class DataProvider(ABC):
    @abstractmethod
    def get_teams(self) -> List[Dict[str, Any]]:
        """Return a list of teams to initialize a league."""
        pass

    @abstractmethod
    def get_players(self, teams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return a list of players to initialize a league, belonging to the provided teams."""
        pass


class MockDataProvider(DataProvider):
    def __init__(self, seed: int = 123):
        self.seed = seed
        self.rng = random.Random(seed)

    def get_teams(self) -> List[Dict[str, Any]]:
        # A list of 20 realistic Spanish-style club names
        team_names = [
            "Real Madrid", "FC Barcelona", "Atlético Madrid", "Real Sociedad",
            "Villarreal", "Real Betis", "Sevilla FC", "Athletic Club",
            "Getafe CF", "Valencia CF", "CA Osasuna", "Rayo Vallecano",
            "Girona FC", "RCD Mallorca", "RC Celta", "UD Almería",
            "Cádiz CF", "Granada CF", "Deportivo Alavés", "UD Las Palmas"
        ]

        teams = []
        for i, name in enumerate(team_names):
            # Assign strength levels (5: Elite, 4: Strong, 3: Mid, 2: Lower, 1: Relegation candidate)
            if i < 3:
                level = 5
                strength = round(self.rng.uniform(0.9, 1.0), 2)
            elif i < 8:
                level = 4
                strength = round(self.rng.uniform(0.8, 0.89), 2)
            elif i < 14:
                level = 3
                strength = round(self.rng.uniform(0.7, 0.79), 2)
            elif i < 18:
                level = 2
                strength = round(self.rng.uniform(0.6, 0.69), 2)
            else:
                level = 1
                strength = round(self.rng.uniform(0.5, 0.59), 2)

            teams.append({
                "name": name,
                "external_team_id": f"team_{i+1:03d}",
                "level": level,
                "strength": strength
            })
        return teams

    def get_players(self, teams: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        # Lists of first names and last names to generate realistic-looking Spanish football players
        first_names = [
            "Álvaro", "Carlos", "David", "Diego", "Eduardo", "Francisco", "Gonzalo",
            "Hugo", "Iker", "Javier", "Jorge", "José", "Juan", "Luis", "Manuel",
            "Mario", "Miguel", "Pablo", "Pedro", "Roberto", "Sergio", "Tomás",
            "Adrián", "Alejandro", "Daniel", "Fernando", "Gabriel", "Marcos"
        ]
        last_names = [
            "García", "Fernández", "González", "Rodríguez", "López", "Martínez",
            "Sánchez", "Pérez", "Gómez", "Martín", "Jiménez", "Ruiz", "Hernández",
            "Díaz", "Moreno", "Muñoz", "Álvarez", "Romero", "Alonso", "Gutiérrez",
            "Torres", "Domínguez", "Ramos", "Vázquez", "Ramírez", "Gil"
        ]

        players = []

        # We generate a squad for each team:
        # 2 Goalkeepers, 7 Defenders, 7 Midfielders, 5 Forwards = 21 players per team
        # Total = 420 players

        for team in teams:
            club_name = team["name"]
            level = team["level"]

            squad_distribution = [
                ("GK", 2),
                ("DF", 7),
                ("MF", 7),
                ("FW", 5)
            ]

            for pos, count in squad_distribution:
                for squad_idx in range(count):
                    # Generate name
                    fname = self.rng.choice(first_names)
                    lname = self.rng.choice(last_names)
                    player_name = f"{fname} {lname}"

                    # Determine price based on position and team level
                    # Higher level teams have more expensive/highly-rated players
                    base_price = {
                        "GK": 1000000,
                        "DF": 1500000,
                        "MF": 2000000,
                        "FW": 3000000
                    }[pos]

                    multiplier = level * self.rng.uniform(0.8, 1.3)
                    price = round(base_price * multiplier, -4) # round to nearest 10k

                    # Determine expected points (xP)
                    # Higher level team players and forwards/midfielders have higher base xP
                    base_xp = {
                        "GK": 3.5,
                        "DF": 3.8,
                        "MF": 4.2,
                        "FW": 4.8
                    }[pos]

                    xp = round(base_xp * (level / 3.0) * self.rng.uniform(0.9, 1.1), 1)
                    # Ensure minimum xP
                    xp = max(1.0, xp)

                    # Form multiplier
                    form = round(self.rng.uniform(0.85, 1.15), 2)

                    # Play probability (tier players are more likely to play)
                    # Goalkeepers: 1 is regular (1.0), 1 is sub (0.05)
                    # Others: some regular (0.9), some sub/rotational (0.4), some reserves (0.1)
                    if pos == "GK":
                        play_prob = 1.0 if squad_idx == 0 else 0.05
                    else:
                        if squad_idx < 4:
                            play_prob = 0.9
                        elif squad_idx < 6:
                            play_prob = 0.4
                        else:
                            play_prob = 0.1

                    players.append({
                        "name": player_name,
                        "position": pos,
                        "club_name": club_name,
                        "price": float(price),
                        "market_value": float(price),
                        "xp": float(xp),
                        "form": float(form),
                        "play_probability": float(play_prob),
                        "status": "healthy"
                    })

        return players
