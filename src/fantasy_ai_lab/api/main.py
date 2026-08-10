import os
import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fantasy_ai_lab.database.connection import get_db, engine, Base
from fantasy_ai_lab.config import settings
from fantasy_ai_lab.database.models import (
    SimulationJob, Simulation, League, Manager, Player, Roster, Lineup,
    Snapshot, Decision, Situation, Outcome, Reward, Event, Transaction,
    Evaluation, Tournament, StrategyVersion
)
from fantasy_ai_lab.simulator.jobs import JobService
from fantasy_ai_lab.simulator.snapshots import SnapshotService
from fantasy_ai_lab.simulator.counterfactuals import CounterfactualService
from fantasy_ai_lab.simulator.events import EventEngine
from fantasy_ai_lab.knowledge.memory import KnowledgeService
from fantasy_ai_lab.training.evaluation import EvaluationService
from fantasy_ai_lab.training.tournaments import TournamentService
from fantasy_ai_lab.workers.runner import SimulationWorker
from fantasy_ai_lab.workers.continuous import ContinuousTrainingWorker
from fantasy_ai_lab.integration.github_actions import (
    GitHubActionsClient,
    GitHubActionsError,
)

app = FastAPI(
    title="Fantasy AI Lab API",
    description="Autonomous simulation, learning, and strategy system for Fantasy Football",
    version="1.0.0"
)

# Local/test fallback only. Production schema changes still go through Alembic.
if settings.ENV == "development":
    Base.metadata.create_all(bind=engine)

# Pydantic schemas for request validation
class JobCreate(BaseModel):
    seed: int = Field(123, description="Master seed for the simulation")
    leagues_total: int = Field(5, ge=1, description="Total leagues to simulate")
    matchdays: int = Field(5, ge=1, le=38, description="Matchdays per league")
    extreme_matchday: Optional[int] = Field(None, ge=1, le=38)
    extreme_scenario: str = "STAR_PLAYER_INJURED"
    configuration: Optional[Dict[str, Any]] = Field(None, description="Additional job parameters")

class SnapshotCreate(BaseModel):
    matchday_number: int = Field(..., description="Matchday number for snapshot")
    description: Optional[str] = Field(None, description="Optional description")

class ForkRequest(BaseModel):
    new_league_name: str = Field(..., description="Name for the newly forked league")

class RunBatchRequest(BaseModel):
    max_leagues: int = Field(1, ge=1, le=1000)
    retry: bool = False

class ContinuousCycleRequest(BaseModel):
    seed: int = 123
    leagues_total: int = Field(1, ge=1, le=10000)
    matchdays: int = Field(1, ge=1, le=38)
    batch_size: int = Field(1, ge=1, le=1000)
    strategy_name: Optional[str] = None
    strategy_version: str = "v1.0"
    configuration: Dict[str, Any] = Field(default_factory=dict)

class DecisionRequest(BaseModel):
    leagueState: Dict[str, Any] = Field(default_factory=dict)
    market: Dict[str, Any] = Field(default_factory=dict)
    team: Dict[str, Any] = Field(default_factory=dict)
    lineup: Dict[str, Any] = Field(default_factory=dict)
    context: Dict[str, Any] = Field(default_factory=dict)

class CounterfactualRequest(BaseModel):
    alternatives: List[Dict[str, Any]] = Field(default_factory=list)
    features: Dict[str, Any] = Field(default_factory=dict)
    actions: List[str] = Field(default_factory=list)
    limit: int = Field(100, ge=1, le=1000)

class KnowledgeSearchRequest(BaseModel):
    features: Dict[str, Any] = Field(default_factory=dict)
    limit: int = Field(10, ge=1, le=1000)
    action_type: Optional[str] = None
    strategy_name: Optional[str] = None
    strategy_version: Optional[str] = None
    dataset_name: Optional[str] = None
    max_distance: Optional[float] = Field(None, ge=0.0)

class EvaluationRequest(BaseModel):
    strategy_name: str
    strategy_version: str = "v1.0"
    dataset_name: str = "all"
    league_id: Optional[int] = None

class TournamentRequest(BaseModel):
    name: str
    strategies: List[Dict[str, str]]
    dataset_name: str = "all"

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now(datetime.UTC).isoformat()}

# --- SIMULATIONS ENDPOINTS ---

def _dispatch_inputs(job: SimulationJob) -> Dict[str, str]:
    config = job.configuration or {}
    scenarios = config.get("extreme_scenarios") or {}
    extreme_matchday = next(iter(scenarios), "") if scenarios else ""
    extreme_scenario = scenarios.get(extreme_matchday, "STAR_PLAYER_INJURED") if scenarios else "STAR_PLAYER_INJURED"
    return {
        "job_id": str(job.id),
        "leagues": str(job.leagues_total),
        "matchdays": str(job.matchdays),
        "seed": str(job.seed),
        "extreme_matchday": str(extreme_matchday),
        "extreme_scenario": str(extreme_scenario),
    }


def _dispatch_job(db: Session, job_id: int, retry: bool = False) -> Dict[str, Any]:
    if db.query(SimulationJob).filter_by(id=job_id).first() is None:
        raise HTTPException(status_code=404, detail="SimulationJob not found")
    client = GitHubActionsClient.from_environment()
    if not client.configured:
        # Local development and the existing CLI remain usable without a
        # remote credential. Production must configure ENV=production and
        # fails visibly rather than leaving an unexecutable queue item.
        if os.getenv("ENV", settings.ENV) == "production":
            job = JobService.set_dispatch_state(
                db, job_id, "failed", "GITHUB_TOKEN is not configured"
            )
            raise HTTPException(status_code=503, detail=job.error_message)
        job = JobService.set_dispatch_state(db, job_id, "not_configured")
        return {"accepted": False, "status": job.status, "reason": "GITHUB_TOKEN not configured"}

    job = JobService.claim_dispatch(db, job_id, retry=retry)
    if job is None:
        current = db.query(SimulationJob).filter_by(id=job_id).first()
        if current is None:
            raise HTTPException(status_code=404, detail="SimulationJob not found")
        return {
            "accepted": False,
            "status": current.status,
            "reason": "workflow already requested or job is finalized",
        }
    try:
        client.dispatch(_dispatch_inputs(job))
    except GitHubActionsError as exc:
        failed = JobService.set_dispatch_state(db, job.id, "failed", str(exc))
        raise HTTPException(status_code=502, detail=failed.error_message)
    accepted = JobService.set_dispatch_state(db, job.id, "accepted")
    return {"accepted": True, "status": accepted.status, "ref": client.config.ref}


@app.post("/api/v1/simulations", status_code=201)
def create_simulation_job(payload: JobCreate, db: Session = Depends(get_db)):
    configuration = dict(payload.configuration or {})
    if payload.extreme_matchday is not None:
        configuration["extreme_scenarios"] = {
            str(payload.extreme_matchday): payload.extreme_scenario
        }
    job = JobService.create_job(
        db=db,
        seed=payload.seed,
        leagues_total=payload.leagues_total,
        matchdays=payload.matchdays,
        configuration=configuration,
    )
    dispatch = _dispatch_job(db, job.id)
    return {
        "job_id": job.id,
        "status": job.status,
        "seed": job.seed,
        "leagues_total": job.leagues_total,
        "matchdays": job.matchdays,
        "dispatch": dispatch,
        "created_at": job.created_at.isoformat(),
    }

@app.get("/api/v1/simulations")
def list_simulation_jobs(db: Session = Depends(get_db)):
    jobs = db.query(SimulationJob).order_by(SimulationJob.id.desc()).all()
    return [{
        "job_id": j.id,
        "status": j.status,
        "leagues_completed": j.leagues_completed,
        "leagues_total": j.leagues_total,
        "matchdays": j.matchdays,
        "seed": j.seed,
        "error_message": j.error_message,
        "dispatch": (j.configuration or {}).get("github_dispatch"),
        "created_at": j.created_at.isoformat()
    } for j in jobs]

@app.get("/api/v1/simulations/{id}")
def get_simulation_job(id: int, db: Session = Depends(get_db)):
    job = db.query(SimulationJob).filter_by(id=id).first()
    if not job:
        raise HTTPException(status_code=404, detail="SimulationJob not found")

    simulations = db.query(Simulation).filter_by(job_id=job.id).all()
    leagues = []
    for sim in simulations:
        sim_leagues = db.query(League).filter_by(simulation_id=sim.id).all()
        leagues.extend([{
            "league_id": l.id,
            "name": l.name,
            "matchday": l.matchday,
            "status": l.status
        } for l in sim_leagues])

    return {
        "job_id": job.id,
        "status": job.status,
        "seed": job.seed,
        "leagues_total": job.leagues_total,
        "leagues_completed": job.leagues_completed,
        "matchdays": job.matchdays,
        "current_league_idx": job.current_league_idx,
        "error_message": job.error_message,
        "progress": {
            "leagues_completed": job.leagues_completed,
            "leagues_total": job.leagues_total,
            "current_league_idx": job.current_league_idx,
            "current_matchday_idx": job.current_matchday_idx,
        },
        "dispatch": (job.configuration or {}).get("github_dispatch"),
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "leagues": leagues
    }

@app.post("/api/v1/simulations/{id}/run")
def run_simulation_job(id: int, retry: bool = False, db: Session = Depends(get_db)):
    result = _dispatch_job(db, id, retry=retry)
    return {"job_id": id, **result}


@app.post("/api/v1/simulations/{id}/run-batch")
def run_simulation_batch(id: int, payload: RunBatchRequest, db: Session = Depends(get_db)):
    # Keep the legacy endpoint for the dashboard, but dispatch the full
    # persistent job to GitHub Actions rather than consuming Render CPU.
    result = _dispatch_job(db, id, retry=payload.retry)
    return {"job_id": id, "batch_size": payload.max_leagues, **result}

@app.post("/api/v1/simulations/{id}/cancel")
def cancel_simulation_job(id: int, db: Session = Depends(get_db)):
    try:
        job = JobService.cancel_job(db, id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"job_id": job.id, "status": job.status, "checkpoint": job.checkpoint}

@app.post("/api/v1/training/cycle", status_code=201)
def run_training_cycle(payload: ContinuousCycleRequest, db: Session = Depends(get_db)):
    return ContinuousTrainingWorker.run_cycle(
        db,
        seed=payload.seed,
        leagues_total=payload.leagues_total,
        matchdays=payload.matchdays,
        batch_size=payload.batch_size,
        strategy_name=payload.strategy_name,
        strategy_version=payload.strategy_version,
        configuration=payload.configuration,
    )

# --- LEAGUES ENDPOINTS ---

@app.get("/api/v1/leagues/{id}")
def get_league_details(id: int, db: Session = Depends(get_db)):
    league = db.query(League).filter_by(id=id).first()
    if not league:
        raise HTTPException(status_code=404, detail="League not found")

    managers = db.query(Manager).filter_by(league_id=league.id).order_by(Manager.position).all()
    players_count = db.query(Player).filter_by(league_id=league.id).count()

    return {
        "league_id": league.id,
        "name": league.name,
        "status": league.status,
        "matchday": league.matchday,
        "seed": league.seed,
        "parent_league_id": league.parent_league_id,
        "players_count": players_count,
        "managers": [{
            "id": m.id,
            "name": m.name,
            "strategy_type": m.strategy_type,
            "budget": m.budget,
            "points": m.points,
            "position": m.position
        } for m in managers]
    }

# --- EVENT OPERATIONS ---

@app.get("/api/v1/events/catalog")
def event_catalog():
    """Return the versioned event definitions used by the simulator."""
    return {"events": EventEngine.catalog()}

@app.get("/api/v1/leagues/{id}/events")
def list_league_events(
    id: int,
    matchday: Optional[int] = Query(None, ge=1),
    event_type: Optional[str] = Query(None),
    extreme_only: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    league = db.query(League).filter_by(id=id).first()
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    query = db.query(Event).filter(Event.league_id == id)
    if matchday is not None:
        query = query.filter(Event.matchday_number == matchday)
    if event_type:
        query = query.filter(Event.event_type == event_type)
    if extreme_only:
        query = query.filter(Event.is_extreme.is_(True))
    events = query.order_by(Event.matchday_number, Event.id).limit(limit).all()
    return {
        "league_id": id,
        "sample_size": len(events),
        "events": [{
            "id": event.id,
            "matchday": event.matchday_number,
            "type": event.event_type,
            "player_id": event.target_player_id,
            "manager_id": event.target_manager_id,
            "description": event.description,
            "severity": event.severity,
            "duration": event.duration,
            "impact": event.impact,
            "probability": event.probability,
            "uncertainty": event.uncertainty,
            "consequences": event.consequences,
            "recovery": event.recovery,
            "source": event.source,
            "is_extreme": event.is_extreme,
        } for event in events],
    }

# --- SNAPSHOT OPERATIONS ---

@app.get("/api/v1/leagues/{id}/snapshots")
def list_snapshots(id: int, db: Session = Depends(get_db)):
    snapshots = db.query(Snapshot).filter_by(league_id=id).all()
    return [{
        "snapshot_id": s.id,
        "matchday_number": s.matchday_number,
        "description": s.description,
        "created_at": s.created_at.isoformat()
    } for s in snapshots]

@app.post("/api/v1/leagues/{id}/snapshots", status_code=201)
def create_snapshot(id: int, payload: SnapshotCreate, db: Session = Depends(get_db)):
    try:
        snap = SnapshotService.create_snapshot(
            db=db,
            league_id=id,
            matchday_num=payload.matchday_number,
            description=payload.description
        )
        return {
            "snapshot_id": snap.id,
            "league_id": snap.league_id,
            "matchday_number": snap.matchday_number,
            "description": snap.description,
            "created_at": snap.created_at.isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/snapshots/{id}/restore")
def restore_snapshot(id: int, db: Session = Depends(get_db)):
    try:
        league = SnapshotService.restore_snapshot(db, id)
        return {
            "status": "success",
            "message": f"League {league.id} successfully restored from snapshot {id}.",
            "league": {
                "id": league.id,
                "name": league.name,
                "matchday": league.matchday
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/v1/snapshots/{id}/fork")
def fork_snapshot(id: int, payload: ForkRequest, db: Session = Depends(get_db)):
    try:
        forked_league = SnapshotService.fork_snapshot(db, id, payload.new_league_name)
        return {
            "status": "success",
            "message": f"Snapshot {id} successfully forked into new League {forked_league.id}.",
            "league": {
                "id": forked_league.id,
                "name": forked_league.name,
                "parent_league_id": forked_league.parent_league_id,
                "matchday": forked_league.matchday
            }
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- FANTASY-MANAGER INTEGRATION ENDPOINTS ---

@app.post("/api/v1/decision")
def get_recommendation(payload: DecisionRequest, db: Session = Depends(get_db)):
    """Return a read-only recommendation grounded in persisted similar cases."""
    player_id = payload.context.get("playerId", "unknown")
    player_name = payload.context.get("playerName", "unnamed")
    player_price = float(payload.context.get("playerPrice", 1000000.0) or 0.0)
    query_features = {
        "playerPrice": player_price,
        "budget": float(payload.team.get("budget", payload.context.get("budget", 0.0)) or 0.0),
        "matchday": float(payload.leagueState.get("matchday", 0.0) or 0.0),
        "roster_count": float(payload.team.get("roster_count", 0.0) or 0.0),
        "action_context": payload.context.get("action", "BUY"),
    }
    historical_memory = KnowledgeService.recommend(db, query_features, limit=10)
    winner = historical_memory["ranking"][0] if historical_memory["ranking"] else None
    recommended_action = winner["action"] if winner else "HOLD"
    confidence = float(winner["decision_confidence"]) if winner else 0.0
    if winner:
        explanation = (
            f"La acción {recommended_action} aparece en {winner['sample_size']} situaciones similares; "
            f"{winner['outcome_sample_size']} tienen resultado persistido y su recompensa media es "
            f"{winner['average_reward']}."
        )
    else:
        explanation = "No hay situaciones históricas comparables; no se inventa una estadística y se recomienda HOLD."

    return {
        "recommendedAction": recommended_action,
        "playerId": player_id,
        "playerName": player_name,
        "amount": round(player_price * 1.05, -4) if recommended_action == "BUY" else None,
        "confidence": confidence,
        "explanation": explanation,
        "similarCases": historical_memory["cases"],
        "sampleSize": historical_memory["sample_size"],
        "historicalMemory": historical_memory,
        "strategyVersion": "v1.0",
    }

@app.post("/api/v1/decisions/{id}/counterfactuals")
def create_counterfactuals(id: int, payload: CounterfactualRequest, db: Session = Depends(get_db)):
    decision = db.query(Decision).filter_by(id=id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    CounterfactualService.evaluate(db, decision, payload.alternatives)
    db.commit()
    return CounterfactualService.compare(db, id)

@app.post("/api/v1/decisions/{id}/counterfactuals/from-memory")
def create_memory_counterfactuals(id: int, payload: CounterfactualRequest, db: Session = Depends(get_db)):
    decision = db.query(Decision).filter_by(id=id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found")
    actions = payload.actions or ["BUY", "SELL", "HOLD"]
    CounterfactualService.evaluate_from_memory(db, decision, payload.features, actions, payload.limit)
    db.commit()
    return CounterfactualService.compare(db, id)

@app.get("/api/v1/decisions/{id}/counterfactuals")
def list_counterfactuals(id: int, db: Session = Depends(get_db)):
    try:
        return CounterfactualService.compare(db, id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

@app.post("/api/v1/evaluate", status_code=201)
def evaluate_strategy(payload: EvaluationRequest, db: Session = Depends(get_db)):
    evaluation = EvaluationService.evaluate_strategy(
        db,
        strategy_name=payload.strategy_name,
        strategy_version=payload.strategy_version,
        dataset_name=payload.dataset_name,
        league_id=payload.league_id,
    )
    return {
        "evaluation_id": evaluation.id,
        "status": evaluation.status,
        "sample_size": evaluation.sample_size,
        "metrics": evaluation.metrics,
    }

@app.post("/api/v1/tournaments", status_code=201)
def run_tournament(payload: TournamentRequest, db: Session = Depends(get_db)):
    tournament = TournamentService.run(db, payload.name, payload.strategies, payload.dataset_name)
    return {"tournament_id": tournament.id, "status": tournament.status, "rankings": tournament.rankings}

@app.post("/api/v1/simulate")
def execute_real_time_simulation():
    return {"status": "success", "message": "On-demand simulation endpoint ready."}

@app.get("/api/v1/strategy/current")
def get_current_strategy():
    return {"strategy": "BalancedAgent", "version": "v1.0", "parameters": {"riskTolerance": 0.5}}

@app.get("/api/v1/strategy/history")
def get_strategy_history():
    return [{"version": "v1.0", "deployed_at": datetime.datetime.now(datetime.UTC).isoformat()}]

@app.get("/api/v1/knowledge/similar")
def search_similar_situations(
    price: float = Query(1000000.0),
    limit: int = Query(10, ge=1, le=1000),
    action_type: Optional[str] = Query(None),
    strategy_name: Optional[str] = Query(None),
    strategy_version: Optional[str] = Query(None),
    dataset_name: Optional[str] = Query(None),
    max_distance: Optional[float] = Query(None, ge=0.0),
    db: Session = Depends(get_db),
):
    """Search nearest historical cases and aggregate evidence by action."""
    features = {"playerPrice": price}
    return {
        "query_features": features,
        **KnowledgeService.recommend(
            db,
            features,
            limit=limit,
            action_type=action_type,
            strategy_name=strategy_name,
            strategy_version=strategy_version,
            dataset_name=dataset_name,
            max_distance=max_distance,
        ),
    }

@app.post("/api/v1/knowledge/similar")
def search_similar_situations_post(payload: KnowledgeSearchRequest, db: Session = Depends(get_db)):
    """Search situations using the complete real-world feature payload."""
    return {
        "query_features": payload.features,
        **KnowledgeService.recommend(
            db,
            payload.features,
            limit=payload.limit,
            action_type=payload.action_type,
            strategy_name=payload.strategy_name,
            strategy_version=payload.strategy_version,
            dataset_name=payload.dataset_name,
            max_distance=payload.max_distance,
        ),
    }

# --- WEB DASHBOARD ---

@app.get("/dashboard/legacy", response_class=HTMLResponse)
def dashboard_view(db: Session = Depends(get_db)):
    # Gather statistics
    jobs = db.query(SimulationJob).order_by(SimulationJob.id.desc()).all()
    leagues = db.query(League).order_by(League.id.desc()).all()
    snapshots = db.query(Snapshot).order_by(Snapshot.id.desc()).all()
    decisions = db.query(Decision).order_by(Decision.id.desc()).limit(15).all()

    # Built HTML template
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Fantasy AI Lab — Dashboard</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body { background-color: #f8f9fa; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
            .card { border-radius: 10px; border: none; box-shadow: 0 4px 6px rgba(0,0,0,0.05); margin-bottom: 20px; }
            .navbar { background-color: #1e293b; }
            .hero { background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: white; padding: 30px 20px; border-radius: 10px; margin-bottom: 30px; }
        </style>
    </head>
    <body>
        <nav class="navbar navbar-dark mb-4">
            <div class="container">
                <a class="navbar-brand font-weight-bold" href="#">🧪 FANTASY AI LAB</a>
                <span class="navbar-text text-white-50">Sistema de simulación y estrategia de IA</span>
            </div>
        </nav>

        <div class="container">
            <div class="hero">
                <h1 class="display-5">Laboratorio de Aprendizaje Fantasy</h1>
                <p class="lead">Simula miles de ligas, refina estrategias de IA, busca situaciones históricas y devuelve recomendaciones.</p>
                <div class="mt-3">
                    <span class="badge bg-success py-2 px-3">Modo: Fases 1–4 operativas</span>
                    <span class="badge bg-light text-dark py-2 px-3 ms-2">Base de Datos: SQL/ORM Configurado</span>
                </div>
            </div>

            <div class="row">
                <div class="col-md-4">
                    <div class="card p-3 bg-white text-center">
                        <h6 class="text-uppercase text-muted">Ligas en BD</h6>
                        <h2 class="display-6 font-weight-bold">""" + str(len(leagues)) + """</h2>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card p-3 bg-white text-center">
                        <h6 class="text-uppercase text-muted">Trabajos de Simulación</h6>
                        <h2 class="display-6 font-weight-bold">""" + str(len(jobs)) + """</h2>
                    </div>
                </div>
                <div class="col-md-4">
                    <div class="card p-3 bg-white text-center">
                        <h6 class="text-uppercase text-muted">Snapshots de Jornadas</h6>
                        <h2 class="display-6 font-weight-bold">""" + str(len(snapshots)) + """</h2>
                    </div>
                </div>
            </div>

            <div class="row">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-header bg-dark text-white font-weight-bold">Trabajos de Simulación (Simulation Jobs)</div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-hover">
                                    <thead>
                                        <tr>
                                            <th>ID</th>
                                            <th>Semilla (Seed)</th>
                                            <th>Progreso</th>
                                            <th>Ligas Totales</th>
                                            <th>Jornadas</th>
                                            <th>Estado</th>
                                        </tr>
                                    </thead>
                                    <tbody>
    """
    for j in jobs:
        progress = f"{j.leagues_completed}/{j.leagues_total}"
        status_color = "success" if j.status == "completed" else "warning" if j.status == "running" else "secondary"
        html_content += f"""
                                        <tr>
                                            <td>{j.id}</td>
                                            <td><code>{j.seed}</code></td>
                                            <td>{progress}</td>
                                            <td>{j.leagues_total}</td>
                                            <td>{j.matchdays}</td>
                                            <td><span class="badge bg-{status_color}">{j.status.upper()}</span></td>
                                        </tr>
        """

    html_content += """
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>

                    <div class="card">
                        <div class="card-header bg-dark text-white font-weight-bold">Ligas Simuladas Activas / Históricas</div>
                        <div class="card-body">
                            <div class="table-responsive">
                                <table class="table table-hover">
                                    <thead>
                                        <tr>
                                            <th>ID</th>
                                            <th>Nombre de Liga</th>
                                            <th>Jornada Actual</th>
                                            <th>Estado</th>
                                        </tr>
                                    </thead>
                                    <tbody>
    """
    for l in leagues:
        status_badge = "success" if l.status == "completed" else "primary"
        html_content += f"""
                                        <tr>
                                            <td>{l.id}</td>
                                            <td>{l.name}</td>
                                            <td>Jornada {l.matchday}</td>
                                            <td><span class="badge bg-{status_badge}">{l.status.upper()}</span></td>
                                        </tr>
        """

    html_content += """
                                    </tbody>
                                </table>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="col-md-4">
                    <div class="card">
                        <div class="card-header bg-dark text-white font-weight-bold">Últimas Decisiones de IA</div>
                        <div class="card-body p-0">
                            <ul class="list-group list-group-flush">
    """
    for d in decisions:
        action_badge = "info" if d.action_type == "LINEUP" else "success" if d.action_type == "BUY" else "danger"
        amount_str = f" por {d.amount:,.0f} €" if d.amount else ""
        html_content += f"""
                                <li class="list-group-item">
                                    <div class="d-flex w-100 justify-content-between">
                                        <h6 class="mb-1">Manager {d.manager_id}</h6>
                                        <small class="text-muted">Jornada {d.matchday_number}</small>
                                    </div>
                                    <p class="mb-1">Acción: <span class="badge bg-{action_badge}">{d.action_type}</span>{amount_str}</p>
                                    <small class="text-muted">Confianza: {d.confidence:.2f} | Versión: {d.strategy_version}</small>
                                </li>
        """
    if not decisions:
        html_content += """
                                <li class="list-group-item text-center text-muted">No se han registrado decisiones todavía.</li>
        """

    html_content += """
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        <footer class="text-center text-muted py-5 mt-5">
            <p>Fantasy AI Lab &copy; 2025. Arquitectura del Laboratorio de Experimentación de Estrategias.</p>
        </footer>
    </body>
    </html>
    """
    return html_content


@app.get("/api/v1/dashboard/overview")
def dashboard_overview(db: Session = Depends(get_db)):
    jobs = db.query(SimulationJob).order_by(SimulationJob.id.desc()).limit(25).all()
    return {
        "metrics": {
            "jobs": db.query(SimulationJob).count(),
            "active_jobs": db.query(SimulationJob).filter(SimulationJob.status.in_(["pending", "running", "partial"])).count(),
            "completed_leagues": sum(int(job.leagues_completed or 0) for job in jobs),
            "leagues": db.query(League).count(),
            "evaluations": db.query(Evaluation).count(),
            "tournaments": db.query(Tournament).count(),
        },
        "jobs": [{
            "job_id": job.id,
            "status": job.status,
            "seed": job.seed,
            "leagues_completed": job.leagues_completed,
            "leagues_total": job.leagues_total,
            "matchdays": job.matchdays,
            "progress": round((job.leagues_completed / job.leagues_total) * 100, 1) if job.leagues_total else 0.0,
            "checkpoint": job.checkpoint or {},
            "error_message": job.error_message,
            "dispatch": (job.configuration or {}).get("github_dispatch"),
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "completed_at": job.completed_at.isoformat() if job.completed_at else None,
            "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        } for job in jobs],
    }


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_control_view():
    return HTMLResponse(content="""
<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fantasy AI Lab · Control room</title>
  <style>
    :root { color-scheme: dark; --bg:#08111f; --panel:#101d2f; --line:#243752; --muted:#8ea3bd; --text:#edf5ff; --accent:#63e6be; --blue:#71a7ff; --danger:#ff7b86; }
    * { box-sizing:border-box; } body { margin:0; background:radial-gradient(circle at 80% 0%,#17345a 0,#08111f 42%); color:var(--text); font:15px/1.5 Inter,ui-sans-serif,system-ui,sans-serif; }
    .shell { max-width:1200px; margin:auto; padding:32px 20px 56px; } header { display:flex; justify-content:space-between; gap:20px; align-items:end; margin-bottom:28px; }
    h1 { font-size:clamp(2rem,4vw,3.6rem); line-height:1; margin:8px 0 12px; letter-spacing:-.05em; } h2 { margin:0 0 14px; font-size:1.1rem; } p { color:var(--muted); margin:0; } .eyebrow { color:var(--accent); font-weight:700; letter-spacing:.12em; text-transform:uppercase; font-size:.72rem; }
    .pill { border:1px solid #2b4565; color:var(--blue); border-radius:999px; padding:7px 12px; white-space:nowrap; font-size:.82rem; }
    .grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin-bottom:18px; } .card { background:linear-gradient(145deg,rgba(20,38,61,.96),rgba(11,23,39,.96)); border:1px solid var(--line); border-radius:16px; padding:18px; box-shadow:0 14px 40px rgba(0,0,0,.18); } .metric b { display:block; font-size:2rem; margin-top:8px; } .metric span { color:var(--muted); font-size:.78rem; text-transform:uppercase; letter-spacing:.08em; }
    .layout { display:grid; grid-template-columns:330px 1fr; gap:18px; } label { display:block; color:var(--muted); font-size:.8rem; margin:12px 0 5px; } input { width:100%; padding:10px 11px; border:1px solid var(--line); border-radius:9px; background:#0b1727; color:var(--text); } button { border:0; border-radius:9px; padding:10px 13px; color:#06121d; background:var(--accent); font-weight:700; cursor:pointer; transition:transform .15s,filter .15s; } button:hover { transform:translateY(-1px); filter:brightness(1.08); } button.secondary { color:var(--text); background:#213651; } button.danger { color:#fff; background:#8d3348; } .form-actions { display:flex; gap:8px; margin-top:16px; }
    table { width:100%; border-collapse:collapse; } th,td { padding:12px 8px; text-align:left; border-bottom:1px solid var(--line); vertical-align:middle; } th { color:var(--muted); font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; } .status { display:inline-flex; align-items:center; gap:6px; border-radius:999px; padding:4px 8px; font-size:.72rem; font-weight:700; } .status.running { color:#08111f; background:var(--accent); } .status.completed { color:#08111f; background:#8cc8ff; } .status.partial,.status.pending { color:#ffe4a3; background:#55441d; } .status.cancelled,.status.failed { color:#ffd7db; background:#542a38; } .bar { height:7px; min-width:90px; border-radius:99px; background:#1b2b43; overflow:hidden; } .bar i { display:block; height:100%; background:linear-gradient(90deg,var(--blue),var(--accent)); border-radius:inherit; } .actions { display:flex; gap:6px; flex-wrap:wrap; } .actions button { padding:7px 9px; font-size:.75rem; } #notice { min-height:24px; color:var(--accent); margin:12px 0; } @media(max-width:850px) { .grid { grid-template-columns:repeat(2,1fr); } .layout { grid-template-columns:1fr; } header { align-items:start; flex-direction:column; } } @media(max-width:520px) { .grid { grid-template-columns:1fr 1fr; } .card { padding:14px; } th:nth-child(2),td:nth-child(2) { display:none; } }
  </style>
</head>
<body>
<main class="shell">
  <header><div><div class="eyebrow">Fantasy AI Lab · control room</div><h1>Simulations under control.</h1><p>Launch bounded batches, inspect checkpoints, and monitor progress without executing real Fantasy actions.</p></div><div class="pill">READ / SIMULATE ONLY</div></header>
  <section class="grid" id="metrics"></section>
  <div id="notice"></div>
  <section class="layout">
    <div class="card"><h2>New simulation job</h2><p>Each batch is checkpointed by league and can be resumed safely.</p><form id="create-form"><label>Master seed<input name="seed" type="number" value="123"></label><label>Leagues<input name="leagues_total" type="number" min="1" value="5"></label><label>Matchdays<input name="matchdays" type="number" min="1" max="38" value="5"></label><div class="form-actions"><button type="submit">Create job</button><button class="secondary" type="button" onclick="refresh()">Refresh</button></div></form></div>
    <div class="card"><div style="display:flex;justify-content:space-between;gap:12px;align-items:center"><div><h2>Simulation queue</h2><p>Polling persistent state every 5 seconds.</p></div><span class="pill" id="last-update">—</span></div><div style="overflow:auto"><table><thead><tr><th>Job</th><th>Seed</th><th>Progress</th><th>Status</th><th>Controls</th></tr></thead><tbody id="jobs"><tr><td colspan="5">Loading…</td></tr></tbody></table></div></div>
  </section>
</main>
<script>
const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#039;'}[c]));
let pollTimer;
async function refresh(){ const res=await fetch('/api/v1/dashboard/overview'); const data=await res.json(); const m=data.metrics; document.querySelector('#metrics').innerHTML=[['Jobs',m.jobs],['Active',m.active_jobs],['Completed leagues',m.completed_leagues],['Leagues',m.leagues],['Evaluations',m.evaluations],['Tournaments',m.tournaments]].map(x=>`<div class="card metric"><span>${x[0]}</span><b>${x[1]}</b></div>`).join(''); document.querySelector('#jobs').innerHTML=data.jobs.length?data.jobs.map(j=>`<tr><td>#${j.job_id}</td><td><code>${esc(j.seed)}</code></td><td><div style="display:flex;gap:9px;align-items:center"><div class="bar"><i style="width:${j.progress}%"></i></div><small>${j.leagues_completed}/${j.leagues_total}</small></div></td><td><span class="status ${esc(j.status)}" title="${esc(j.error_message||'')}">${esc(j.status)}</span>${j.error_message?`<small style="display:block;color:var(--danger);max-width:220px">${esc(j.error_message)}</small>`:''}</td><td class="actions">${['completed','cancelled','failed'].includes(j.status)?'':`<button onclick="runJob(${j.job_id})">Run batch</button><button class="danger" onclick="cancelJob(${j.job_id})">Cancel</button>`}</td></tr>`).join(''):'<tr><td colspan="5">No jobs yet.</td></tr>'; document.querySelector('#last-update').textContent=new Date().toLocaleTimeString(); const active=data.jobs.some(j=>['pending','running'].includes(j.status)); if(!active && pollTimer){clearInterval(pollTimer); pollTimer=null;} }
async function startPolling(){ if(!pollTimer){ await refresh(); pollTimer=setInterval(refresh,5000); } }
async function runJob(id){ const res=await fetch(`/api/v1/simulations/${id}/run-batch`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({max_leagues:1})}); const data=await res.json(); document.querySelector('#notice').textContent=data.message||data.detail||`Job #${id} ${data.status}`; startPolling(); }
async function cancelJob(id){ const res=await fetch(`/api/v1/simulations/${id}/cancel`,{method:'POST'}); document.querySelector('#notice').textContent=`Job #${id} ${(await res.json()).status}`; refresh(); }
document.querySelector('#create-form').addEventListener('submit',async(e)=>{e.preventDefault(); const f=new FormData(e.target); const body={seed:Number(f.get('seed')),leagues_total:Number(f.get('leagues_total')),matchdays:Number(f.get('matchdays'))}; const res=await fetch('/api/v1/simulations',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}); const data=await res.json(); document.querySelector('#notice').textContent=data.detail||`Created job #${data.job_id} · ${data.dispatch?.accepted?'GitHub Actions requested':'pending local configuration'}`; startPolling();}); startPolling();
</script>
</body></html>
""")
