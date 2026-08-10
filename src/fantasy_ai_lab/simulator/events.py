import random
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.fantasy_ai_lab.database.models import Event, Player, Manager

class EventEngine:
    def __init__(self, seed: int = 123):
        self.seed = seed
        self.rng = random.Random(seed)

    def trigger_scheduled_scenario(self, db: Session, league_id: int, matchday_num: int, scenario_name: str) -> List[Event]:
        """
        Manually trigger a specific extreme scenario (e.g., STAR_PLAYER_INJURED or MARKET_CRASH).
        Modifies database player/league state and returns created Event models.
        """
        events = []
        if scenario_name == "STAR_PLAYER_INJURED":
            # Find the highest value player in the league and injure them gravely
            star_player = db.query(Player).filter(
                Player.league_id == league_id,
                Player.status == "healthy"
            ).order_by(Player.price.desc()).first()

            if star_player:
                star_player.status = "injured_grave"
                star_player.status_duration = self.rng.randint(3, 6) # injured for 3-6 matchdays
                star_player.play_probability = 0.0

                # Dropping price slightly due to injury
                old_price = star_player.price
                star_player.price = round(star_player.price * 0.85, -4)
                star_player.market_value = star_player.price

                evt = Event(
                    league_id=league_id,
                    matchday_number=matchday_num,
                    event_type="STAR_PLAYER_INJURED",
                    target_player_id=star_player.id,
                    description=f"¡ESTRELLA LESIONADA! {star_player.name} ({star_player.club_name}) se ha lesionado de gravedad y estará de baja {star_player.status_duration} jornadas. Su precio baja de {old_price:,.0f} € a {star_player.price:,.0f} €.",
                    severity="extreme",
                    duration=star_player.status_duration,
                    impact=-0.15,
                    is_extreme=True
                )
                db.add(evt)
                events.append(evt)

        elif scenario_name == "MARKET_CRASH":
            # Drop everyone's price by 15-25%
            players = db.query(Player).filter(Player.league_id == league_id).all()
            for p in players:
                p.price = round(p.price * self.rng.uniform(0.75, 0.85), -4)
                p.market_value = p.price

            evt = Event(
                league_id=league_id,
                matchday_number=matchday_num,
                event_type="MARKET_CRASH",
                description="¡CRASH DEL MERCADO! Pánico financiero generalizado. El valor de todos los jugadores cae entre un 15% y un 25%.",
                severity="extreme",
                duration=1,
                impact=-0.20,
                is_extreme=True
            )
            db.add(evt)
            events.append(evt)

        db.flush()
        return events

    def generate_random_events(self, db: Session, league_id: int, matchday_num: int) -> List[Event]:
        """
        Generate random events for a matchday with realistic probabilities:
        - Light injury: 5% chance per player (lasts 1 matchday)
        - Grave injury: 1% chance per player (lasts 2-5 matchdays)
        - Suspended: 2% chance per player (lasts 1 matchday)
        - Breakout performance: 2% chance per player (lasts 2 matchdays)
        """
        events = []
        # Sort players by name for 100% stable reproducible simulation order
        players = db.query(Player).filter(Player.league_id == league_id).order_by(Player.name, Player.club_name).all()

        # Update remaining duration on existing statuses
        for p in players:
            if p.status_duration > 0:
                p.status_duration -= 1
                if p.status_duration == 0:
                    # Recovery
                    old_status = p.status
                    p.status = "healthy"
                    p.play_probability = 1.0 if p.position == "GK" else 0.9

                    evt = Event(
                        league_id=league_id,
                        matchday_number=matchday_num,
                        event_type="PLAYER_RECOVERED",
                        target_player_id=p.id,
                        description=f"{p.name} se ha recuperado de su estado ({old_status}) y vuelve a estar disponible al 100%.",
                        severity="info",
                        duration=0,
                        impact=0.0,
                        is_extreme=False
                    )
                    db.add(evt)
                    events.append(evt)

        # Generate new events
        for p in players:
            if p.status != "healthy":
                continue # only healthy players get new events

            rand = self.rng.random()
            if rand < 0.01: # Grave injury
                p.status = "injured_grave"
                p.status_duration = self.rng.randint(2, 5)
                p.play_probability = 0.0
                p.price = round(p.price * 0.90, -4)
                p.market_value = p.price

                evt = Event(
                    league_id=league_id,
                    matchday_number=matchday_num,
                    event_type="PLAYER_INJURED_GRAVE",
                    target_player_id=p.id,
                    description=f"{p.name} ({p.club_name}) sufre una rotura fibrilar grave. Baja estimada: {p.status_duration} jornadas.",
                    severity="warning",
                    duration=p.status_duration,
                    impact=-0.10,
                    is_extreme=False
                )
                db.add(evt)
                events.append(evt)

            elif rand < 0.04: # Light injury
                p.status = "injured_light"
                p.status_duration = 1
                p.play_probability = 0.3

                evt = Event(
                    league_id=league_id,
                    matchday_number=matchday_num,
                    event_type="PLAYER_INJURED_LIGHT",
                    target_player_id=p.id,
                    description=f"{p.name} ({p.club_name}) tiene molestias físicas leves y es duda para esta jornada.",
                    severity="warning",
                    duration=1,
                    impact=-0.05,
                    is_extreme=False
                )
                db.add(evt)
                events.append(evt)

            elif rand < 0.06: # Suspended
                p.status = "suspended"
                p.status_duration = 1
                p.play_probability = 0.0

                evt = Event(
                    league_id=league_id,
                    matchday_number=matchday_num,
                    event_type="PLAYER_SUSPENDED",
                    target_player_id=p.id,
                    description=f"{p.name} ({p.club_name}) cumple sanción por acumulación de tarjetas y no jugará.",
                    severity="warning",
                    duration=1,
                    impact=-0.05,
                    is_extreme=False
                )
                db.add(evt)
                events.append(evt)

            elif rand < 0.08: # Breakout / Star performance
                p.status = "breakout"
                p.status_duration = 2
                p.play_probability = 1.0
                p.price = round(p.price * 1.15, -4)
                p.market_value = p.price

                evt = Event(
                    league_id=league_id,
                    matchday_number=matchday_num,
                    event_type="PLAYER_BREAKOUT",
                    target_player_id=p.id,
                    description=f"¡ESTADO DE GRACIA! {p.name} ({p.club_name}) está rindiendo de forma espectacular. Su precio sube un 15%.",
                    severity="info",
                    duration=2,
                    impact=0.15,
                    is_extreme=False
                )
                db.add(evt)
                events.append(evt)

        db.flush()
        return events
