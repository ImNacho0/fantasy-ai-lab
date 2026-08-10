import os
import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from fantasy_ai_lab.database.connection import get_db, engine, Base
from fantasy_ai_lab.config import settings
from fantasy_ai_lab.database.models import (
    SimulationJob, Simulation, League, Manager, Player, Roster, Lineup,
    Snapshot, Decision, Situation, Outcome, Reward, Event, Transaction,
    Evaluation, StrategyVersion
)
from fantasy_ai_lab.simulator.jobs import JobService
from fantasy_ai_lab.simulator.snapshots import SnapshotService
from fantasy_ai_lab.simulator.counterfactuals import CounterfactualService
from fantasy_ai_lab.simulator.events import EventEngine
from fantasy_ai_lab.knowledge.memory import KnowledgeService
from fantasy_ai_lab.training.evaluation import EvaluationService
from fantasy_ai_lab.training.tournaments import TournamentService

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
    leagues_total: int = Field(5, description="Total leagues to simulate")
    matchdays: int = Field(5, description="Matchdays per league")
    configuration: Optional[Dict[str, Any]] = Field(None, description="Additional job parameters")

class SnapshotCreate(BaseModel):
    matchday_number: int = Field(..., description="Matchday number for snapshot")
    description: Optional[str] = Field(None, description="Optional description")

class ForkRequest(BaseModel):
    new_league_name: str = Field(..., description="Name for the newly forked league")

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

class StrategyVersionRequest(BaseModel):
    strategy_name: str
    version: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    parent_version: Optional[str] = None

class ValidationRequest(BaseModel):
    evaluation_id: int
    minimum_sample_size: int = Field(1, ge=1)
    baseline_mean: Optional[float] = None

class PromotionRequest(BaseModel):
    evaluation_id: int

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.now(datetime.UTC).isoformat()}

# --- SIMULATIONS ENDPOINTS ---

@app.post("/api/v1/simulations", status_code=201)
def create_simulation_job(payload: JobCreate, db: Session = Depends(get_db)):
    job = JobService.create_job(
        db=db,
        seed=payload.seed,
        leagues_total=payload.leagues_total,
        matchdays=payload.matchdays,
        configuration=payload.configuration
    )
    return {
        "job_id": job.id,
        "status": job.status,
        "seed": job.seed,
        "leagues_total": job.leagues_total,
        "matchdays": job.matchdays,
        "created_at": job.created_at.isoformat()
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
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "leagues": leagues
    }

def run_job_background(job_id: int):
    # Use localized imports / session to avoid context leakage in worker threads
    from fantasy_ai_lab.database.connection import SessionLocal
    from fantasy_ai_lab.simulator.jobs import JobService
    db_session = SessionLocal()
    try:
        JobService.run_job(db_session, job_id)
    except Exception as e:
        print(f"Background Job {job_id} failed: {e}")
    finally:
        db_session.close()

@app.post("/api/v1/simulations/{id}/run")
def run_simulation_job(id: int, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = db.query(SimulationJob).filter_by(id=id).first()
    if not job:
        raise HTTPException(status_code=404, detail="SimulationJob not found")

    if job.status in ["completed", "failed"]:
        return {"status": job.status, "message": "Job is already finalized."}

    if job.status == "running":
        return {"status": "running", "message": "Job is already active."}

    # Execute in FastAPI Background Task
    background_tasks.add_task(run_job_background, job.id)
    return {"status": "running", "message": "Job execution started in background."}

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

@app.post("/api/v1/strategies/versions", status_code=201)
def register_strategy_version(payload: StrategyVersionRequest, db: Session = Depends(get_db)):
    version = EvaluationService.register_candidate(
        db, payload.strategy_name, payload.version, payload.parameters, payload.parent_version
    )
    return {
        "id": version.id,
        "strategy_name": version.strategy_name,
        "version": version.version,
        "status": version.lifecycle_status,
        "is_active": version.is_active,
    }

@app.get("/api/v1/strategies/versions")
def list_strategy_versions(strategy_name: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(StrategyVersion).order_by(StrategyVersion.strategy_name, StrategyVersion.version)
    if strategy_name:
        query = query.filter(StrategyVersion.strategy_name == strategy_name)
    return [{
        "id": version.id,
        "strategy_name": version.strategy_name,
        "version": version.version,
        "status": version.lifecycle_status,
        "is_active": version.is_active,
        "parent_version": version.parent_version,
        "promoted_at": version.promoted_at.isoformat() if version.promoted_at else None,
    } for version in query.all()]

@app.post("/api/v1/validate", status_code=200)
def validate_strategy(payload: ValidationRequest, db: Session = Depends(get_db)):
    evaluation = db.query(Evaluation).filter_by(id=payload.evaluation_id).first()
    if not evaluation:
        raise HTTPException(status_code=404, detail="Evaluation not found")
    result = EvaluationService.validate_candidate(
        db, evaluation, payload.minimum_sample_size, payload.baseline_mean
    )
    return {"evaluation_id": result.id, "status": result.status, "sample_size": result.sample_size, "metrics": result.metrics}

@app.post("/api/v1/promote", status_code=200)
def promote_strategy(payload: PromotionRequest, db: Session = Depends(get_db)):
    try:
        version = EvaluationService.promote_candidate(db, payload.evaluation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {
        "status": "promoted",
        "strategy_name": version.strategy_name,
        "version": version.version,
        "is_active": version.is_active,
    }

@app.post("/api/v1/simulate")
def execute_real_time_simulation():
    return {"status": "success", "message": "On-demand simulation endpoint ready."}

@app.get("/api/v1/strategy/current")
def get_current_strategy(strategy_name: str = Query("Balanced"), db: Session = Depends(get_db)):
    version = db.query(StrategyVersion).filter_by(strategy_name=strategy_name, is_active=True).order_by(StrategyVersion.id.desc()).first()
    if not version:
        return {"strategy": strategy_name, "version": None, "parameters": {}, "status": "unconfigured"}
    return {"strategy": version.strategy_name, "version": version.version, "parameters": version.parameters or {}, "status": version.lifecycle_status}

@app.get("/api/v1/strategy/history")
def get_strategy_history(strategy_name: Optional[str] = Query(None), db: Session = Depends(get_db)):
    query = db.query(StrategyVersion).order_by(StrategyVersion.created_at.desc())
    if strategy_name:
        query = query.filter(StrategyVersion.strategy_name == strategy_name)
    return [{"strategy": v.strategy_name, "version": v.version, "status": v.lifecycle_status, "is_active": v.is_active, "created_at": v.created_at.isoformat() if v.created_at else None} for v in query.all()]

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

@app.get("/dashboard", response_class=HTMLResponse)
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
