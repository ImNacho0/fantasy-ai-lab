"""Deterministic event engine for injuries, form, roles, and market shocks."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from fantasy_ai_lab.database.models import Event, Player, Manager


@dataclass(frozen=True)
class EventDefinition:
    name: str
    probability: float
    duration_min: int
    duration_max: int
    impact: float
    uncertainty: float
    severity: str = "info"
    is_extreme: bool = False

    def as_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "probability": self.probability,
            "duration": [self.duration_min, self.duration_max],
            "impact": self.impact,
            "uncertainty": self.uncertainty,
            "severity": self.severity,
            "is_extreme": self.is_extreme,
        }


class EventEngine:
    """Generate and apply reproducible events without global random state."""

    CATALOG: Dict[str, EventDefinition] = {
        "PLAYER_INJURED_LIGHT": EventDefinition("PLAYER_INJURED_LIGHT", 0.030, 1, 1, -0.05, 0.20, "warning"),
        "PLAYER_INJURED_GRAVE": EventDefinition("PLAYER_INJURED_GRAVE", 0.010, 2, 5, -0.10, 0.35, "warning"),
        "PLAYER_SUSPENDED": EventDefinition("PLAYER_SUSPENDED", 0.020, 1, 1, -0.05, 0.15, "warning"),
        "PLAYER_BREAKOUT": EventDefinition("PLAYER_BREAKOUT", 0.020, 2, 2, 0.15, 0.30, "info"),
        "PLAYER_FORM_DROP": EventDefinition("PLAYER_FORM_DROP", 0.020, 2, 3, -0.12, 0.30, "warning"),
        "STAR_PLAYER_INJURED": EventDefinition("STAR_PLAYER_INJURED", 1.0, 3, 6, -0.15, 0.25, "extreme", True),
        "MARKET_CRASH": EventDefinition("MARKET_CRASH", 1.0, 1, 1, -0.20, 0.30, "extreme", True),
        "MARKET_BOOM": EventDefinition("MARKET_BOOM", 1.0, 1, 1, 0.20, 0.30, "extreme", True),
        "TEAM_FORM_COLLAPSE": EventDefinition("TEAM_FORM_COLLAPSE", 1.0, 3, 3, -0.20, 0.40, "extreme", True),
        "KEY_PLAYER_LOSES_STARTING_ROLE": EventDefinition("KEY_PLAYER_LOSES_STARTING_ROLE", 1.0, 2, 2, -0.15, 0.25, "warning", True),
        "MANAGER_OVERBID": EventDefinition("MANAGER_OVERBID", 1.0, 1, 1, -0.05, 0.45, "warning", True),
        "PLAYER_RECOVERED": EventDefinition("PLAYER_RECOVERED", 1.0, 0, 0, 0.0, 0.0),
        "TEAM_FORM_RECOVERED": EventDefinition("TEAM_FORM_RECOVERED", 1.0, 0, 0, 0.0, 0.0),
    }

    RANDOM_PLAYER_EVENTS = (
        "PLAYER_INJURED_GRAVE",
        "PLAYER_INJURED_LIGHT",
        "PLAYER_SUSPENDED",
        "PLAYER_BREAKOUT",
        "PLAYER_FORM_DROP",
    )

    def __init__(self, seed: int = 123, probabilities: Optional[Dict[str, float]] = None):
        self.seed = seed
        self.probabilities = dict(probabilities or {})

    @classmethod
    def catalog(cls) -> Dict[str, Dict[str, Any]]:
        return {name: definition.as_dict() for name, definition in cls.CATALOG.items()}

    def _rng(self, *parts: Any) -> random.Random:
        key = ":".join(str(part) for part in (self.seed, *parts))
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        return random.Random(int.from_bytes(digest[:8], "big"))

    @staticmethod
    def _player_key(player: Player) -> tuple[str, str, str]:
        """Return a stable identity that is independent of database auto-increment IDs."""
        return (player.club_name, player.name, player.position)

    def _definition(self, event_type: str) -> EventDefinition:
        try:
            return self.CATALOG[event_type]
        except KeyError as exc:
            raise ValueError(f"Unknown event type: {event_type}") from exc

    def _create_event(
        self,
        db: Session,
        league_id: int,
        matchday_num: int,
        event_type: str,
        description: str,
        *,
        target_player_id: Optional[int] = None,
        target_manager_id: Optional[int] = None,
        duration: Optional[int] = None,
        probability: Optional[float] = None,
        source: str = "random",
        consequences: Optional[Dict[str, Any]] = None,
        recovery: Optional[Dict[str, Any]] = None,
    ) -> Event:
        definition = self._definition(event_type)
        event = Event(
            league_id=league_id,
            matchday_number=matchday_num,
            event_type=event_type,
            target_player_id=target_player_id,
            target_manager_id=target_manager_id,
            description=description,
            severity=definition.severity,
            duration=duration if duration is not None else definition.duration_max,
            impact=definition.impact,
            probability=probability if probability is not None else definition.probability,
            uncertainty=definition.uncertainty,
            consequences=consequences or {},
            recovery=recovery or {"status": "pending"},
            source=source,
            is_extreme=definition.is_extreme,
        )
        db.add(event)
        return event

    @staticmethod
    def _duration(definition: EventDefinition, rng: random.Random) -> int:
        return rng.randint(definition.duration_min, definition.duration_max)

    def _apply_player_event(
        self,
        db: Session,
        league_id: int,
        matchday_num: int,
        player: Player,
        event_type: str,
        *,
        source: str = "random",
        probability: Optional[float] = None,
        rng: Optional[random.Random] = None,
    ) -> Event:
        definition = self._definition(event_type)
        local_rng = rng or self._rng("player-event", matchday_num, *self._player_key(player), event_type)
        duration = self._duration(definition, local_rng)
        previous = {
            "status": player.status,
            "play_probability": player.play_probability,
            "form": player.form,
            "xp": player.xp,
            "price": player.price,
        }

        if event_type in ("PLAYER_INJURED_GRAVE", "STAR_PLAYER_INJURED"):
            player.status = "injured_grave"
            player.play_probability = 0.0
            player.price = round(player.price * 0.90, -4)
        elif event_type == "PLAYER_INJURED_LIGHT":
            player.status = "injured_light"
            player.play_probability = 0.3
        elif event_type == "PLAYER_SUSPENDED":
            player.status = "suspended"
            player.play_probability = 0.0
        elif event_type == "PLAYER_BREAKOUT":
            player.status = "breakout"
            player.play_probability = 1.0
            player.price = round(player.price * 1.15, -4)
        elif event_type == "PLAYER_FORM_DROP":
            player.status = "poor_form"
            player.form = round(max(0.5, player.form * 0.70), 2)
            player.xp = round(max(1.0, player.xp * 0.85), 1)
        player.market_value = player.price
        player.status_duration = duration

        return self._create_event(
            db, league_id, matchday_num, event_type,
            f"{player.name} ({player.club_name}) sufre el evento {event_type} durante {duration} jornadas.",
            target_player_id=player.id,
            duration=duration,
            probability=probability,
            source=source,
            consequences={"previous": previous, "current_status": player.status},
            recovery={"status": "pending", "restores": list(previous)},
        )

    def _recover_expired(self, db: Session, league_id: int, matchday_num: int) -> List[Event]:
        recovery_events: List[Event] = []
        players = db.query(Player).filter(Player.league_id == league_id).order_by(Player.id).all()
        for player in players:
            if player.status_duration <= 0 or player.status == "healthy":
                continue
            player.status_duration -= 1
            if player.status_duration == 0:
                old_status = player.status
                source_query = db.query(Event).filter(
                    Event.league_id == league_id,
                    Event.target_player_id == player.id,
                    ~Event.event_type.in_(("PLAYER_RECOVERED",)),
                )
                source_event = source_query.order_by(Event.id.desc()).first()
                previous = (source_event.consequences or {}).get("previous", {}) if source_event else {}
                if old_status == "poor_form" and source_event:
                    player.form = previous.get("form", player.form)
                    player.xp = previous.get("xp", player.xp)
                player.status = previous.get("status", "healthy")
                player.play_probability = previous.get(
                    "play_probability", 1.0 if player.position == "GK" else 0.9
                )
                player.status_duration = 0
                if source_event:
                    source_event.recovery = {
                        **(source_event.recovery or {}),
                        "status": "completed",
                        "recovered_at": matchday_num,
                    }
                recovery_events.append(self._create_event(
                    db, league_id, matchday_num, "PLAYER_RECOVERED",
                    f"{player.name} se recupera de {old_status} y vuelve a estar disponible.",
                    target_player_id=player.id,
                    duration=0,
                    probability=1.0,
                    source="recovery",
                    consequences={"previous_status": old_status},
                    recovery={"status": "completed"},
                ))

        # Restore team form from the exact values captured at scenario time.
        expired = db.query(Event).filter(
            Event.league_id == league_id,
            Event.event_type == "TEAM_FORM_COLLAPSE",
            Event.matchday_number + Event.duration <= matchday_num,
        ).all()
        for event in expired:
            if (event.recovery or {}).get("status") == "completed":
                continue
            previous = (event.consequences or {}).get("previous", [])
            for item in previous:
                player = db.query(Player).filter_by(id=item["player_id"], league_id=league_id).first()
                if player:
                    player.form = item["form"]
                    player.xp = item["xp"]
            event.recovery = {"status": "completed", "recovered_at": matchday_num}
            recovery_events.append(self._create_event(
                db, league_id, matchday_num, "TEAM_FORM_RECOVERED",
                "El equipo afectado por el colapso de forma recupera sus valores anteriores.",
                duration=0, probability=1.0, source="recovery",
                consequences={"source_event_id": event.id}, recovery={"status": "completed"},
            ))
        return recovery_events

    def _apply_global_scenario(self, db: Session, league_id: int, matchday_num: int, event_type: str) -> List[Event]:
        definition = self._definition(event_type)
        rng = self._rng("scenario", matchday_num, event_type)
        players = db.query(Player).filter(Player.league_id == league_id).order_by(Player.name, Player.id).all()
        events: List[Event] = []

        if event_type == "STAR_PLAYER_INJURED":
            star = max(players, key=lambda player: (player.xp, player.price, -player.id), default=None)
            if star and star.status == "healthy":
                events.append(self._apply_player_event(
                    db, league_id, matchday_num, star, event_type,
                    source="scheduled", probability=1.0, rng=rng,
                ))
                events[-1].severity = definition.severity
                events[-1].is_extreme = True
                events[-1].description = f"ESTRELLA LESIONADA: {star.name} estará de baja {star.status_duration} jornadas."
            return events

        if event_type in ("MARKET_CRASH", "MARKET_BOOM"):
            multiplier_range = (0.75, 0.85) if event_type == "MARKET_CRASH" else (1.15, 1.25)
            changes = []
            for player in players:
                old_price = player.price
                multiplier = rng.uniform(*multiplier_range)
                player.price = round(max(200000.0, player.price * multiplier), -4)
                player.market_value = player.price
                changes.append({"player_id": player.id, "from": old_price, "to": player.price})
            events.append(self._create_event(
                db, league_id, matchday_num, event_type,
                "El mercado sufre un shock global de precios.",
                duration=definition.duration_max, probability=1.0, source="scheduled",
                consequences={"players_affected": len(changes), "changes": changes},
            ))
            return events

        if event_type == "TEAM_FORM_COLLAPSE":
            clubs = sorted({player.club_name for player in players})
            club = clubs[0] if clubs else None
            previous = []
            for player in players:
                if player.club_name == club:
                    previous.append({"player_id": player.id, "form": player.form, "xp": player.xp})
                    player.form = round(max(0.5, player.form * 0.70), 2)
                    player.xp = round(max(1.0, player.xp * 0.80), 1)
            events.append(self._create_event(
                db, league_id, matchday_num, event_type,
                f"El rendimiento de {club or 'un club'} colapsa temporalmente.",
                duration=definition.duration_max, probability=1.0, source="scheduled",
                consequences={"club": club, "previous": previous},
            ))
            return events

        if event_type == "KEY_PLAYER_LOSES_STARTING_ROLE":
            target = max(players, key=lambda player: (player.xp, player.price, -player.id), default=None)
            if target:
                previous = {
                    "status": target.status,
                    "play_probability": target.play_probability,
                    "status_duration": target.status_duration,
                }
                target.status = "benched"
                target.play_probability = 0.2
                target.status_duration = definition.duration_max
                events.append(self._create_event(
                    db, league_id, matchday_num, event_type,
                    f"{target.name} pierde temporalmente la titularidad.",
                    target_player_id=target.id, duration=definition.duration_max,
                    probability=1.0, source="scheduled",
                    consequences={"previous": previous},
                ))
            return events

        if event_type == "MANAGER_OVERBID":
            managers = db.query(Manager).filter_by(league_id=league_id).order_by(Manager.budget.desc(), Manager.id).all()
            target = managers[0] if managers else None
            events.append(self._create_event(
                db, league_id, matchday_num, event_type,
                f"{target.name if target else 'Un manager'} sobrepuja en un escenario de mercado competitivo.",
                target_manager_id=target.id if target else None,
                duration=1, probability=1.0, source="scheduled",
                consequences={"manager_budget": target.budget if target else None},
            ))
            return events

        raise ValueError(f"Unsupported scheduled scenario: {event_type}")

    def trigger_scheduled_scenario(self, db: Session, league_id: int, matchday_num: int, scenario_name: str) -> List[Event]:
        """Apply a named scenario explicitly; scheduled events never use random state."""
        self._definition(scenario_name)
        events = self._recover_expired(db, league_id, matchday_num)
        events.extend(self._apply_global_scenario(db, league_id, matchday_num, scenario_name))
        db.flush()
        return events

    def generate_random_events(self, db: Session, league_id: int, matchday_num: int) -> List[Event]:
        """Generate independent player events and rare global events reproducibly."""
        events = self._recover_expired(db, league_id, matchday_num)
        players = db.query(Player).filter(Player.league_id == league_id).order_by(Player.name, Player.club_name, Player.id).all()
        global_rng = self._rng("global", matchday_num)

        # Rare events are sampled once per league and can be replayed exactly.
        if global_rng.random() < 0.005:
            scenario = ("MARKET_CRASH", "MARKET_BOOM")[global_rng.randrange(2)]
            events.extend(self._apply_global_scenario(db, league_id, matchday_num, scenario))

        for player in players:
            if player.status != "healthy":
                continue
            rng = self._rng("player", matchday_num, *self._player_key(player))
            roll = rng.random()
            cumulative = 0.0
            for event_type in self.RANDOM_PLAYER_EVENTS:
                probability = self.probabilities.get(event_type, self.CATALOG[event_type].probability)
                cumulative += probability
                if roll < cumulative:
                    events.append(self._apply_player_event(
                        db, league_id, matchday_num, player, event_type,
                        source="random", probability=probability, rng=rng,
                    ))
                    break
        db.flush()
        return events
