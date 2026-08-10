import os
import datetime
from typing import Dict, Any, List, Optional
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.fantasy_ai_lab.database.connection import get_db, engine, Base
from src.fantasy_ai_lab.database.models import (
    SimulationJob, Simulation, League, Manager, Player, Roster, Lineup,
    Snapshot, Decision, Situation, Outcome, Reward, Event, Transaction
)
from src.fantasy_ai_lab.simulator.jobs import JobService
from src.fantasy_ai_lab.simulator.snapshots import SnapshotService

app = FastAPI(
    title="Fantasy AI Lab API",
    description="Autonomous simulation, learning, and strategy system for Fantasy Football",
    version="1.0.0"
)

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
    leagueState: Dict[str, Any]
    market: Dict[str, Any]
    team: Dict[str, Any]
    lineup: Dict[str, Any]
    context: Dict[str, Any]

@app.get("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.datetime.utcnow().isoformat()}

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
    from src.fantasy_ai_lab.database.connection import SessionLocal
    from src.fantasy_ai_lab.simulator.jobs import JobService
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
    """
    API prepared for integration with 'fantasy-manager'.
    Returns strategy recommendations based on historical simulated situations.
    """
    # Simple semantic/pattern search mockup:
    # 1. Inspect target player from request context
    player_id = payload.context.get("playerId", "unknown")
    player_name = payload.context.get("playerName", "unnamed")
    player_price = payload.context.get("playerPrice", 1000000.0)

    # 2. Check the DB for similar decisions in past simulations to base recommendation
    similar_decisions = db.query(Decision).filter(
        Decision.action_type == "BUY",
        Decision.amount >= player_price * 0.9,
        Decision.amount <= player_price * 1.1
    ).limit(3).all()

    # If we have similar historical cases, compile results
    outcomes_summary = []
    total_points_gained = 0.0
    for d in similar_decisions:
        out = db.query(Outcome).filter_by(decision_id=d.id).first()
        if out:
            total_points_gained += out.points_gained
            outcomes_summary.append({
                "decision_id": d.id,
                "action": d.action_type,
                "amount": d.amount,
                "points_gained": out.points_gained,
                "wealth_gained": out.wealth_gained
            })

    # Basic recommendation parameters
    confidence = 0.82 if similar_decisions else 0.50
    recommended_action = "BUY" if total_points_gained >= 0 else "HOLD"

    explanation = (
        f"Based on {len(similar_decisions)} similar historical situations with comparable pricing, "
        f"buying players around {player_price:,.0f} € resulted in average positive outcome."
    ) if similar_decisions else "No direct historical match found. Defaulting to standard safety margins."

    return {
        "recommendedAction": recommended_action,
        "playerId": player_id,
        "playerName": player_name,
        "amount": round(player_price * 1.05, -4),
        "confidence": confidence,
        "explanation": explanation,
        "similarCases": outcomes_summary,
        "strategyVersion": "v1.0"
    }

@app.post("/api/v1/evaluate")
def evaluate_strategy():
    return {"status": "success", "message": "Strategy evaluation endpoint ready."}

@app.post("/api/v1/simulate")
def execute_real_time_simulation():
    return {"status": "success", "message": "On-demand simulation endpoint ready."}

@app.get("/api/v1/strategy/current")
def get_current_strategy():
    return {"strategy": "BalancedAgent", "version": "v1.0", "parameters": {"riskTolerance": 0.5}}

@app.get("/api/v1/strategy/history")
def get_strategy_history():
    return [{"version": "v1.0", "deployed_at": datetime.datetime.utcnow().isoformat()}]

@app.get("/api/v1/knowledge/similar")
def search_similar_situations(price: float = Query(1000000.0), db: Session = Depends(get_db)):
    """
    Search database for similar cases of player acquisition and display outcomes.
    """
    cases = db.query(Decision).filter(
        Decision.amount >= price * 0.8,
        Decision.amount <= price * 1.2
    ).limit(10).all()

    results = []
    for c in cases:
        out = db.query(Outcome).filter_by(decision_id=c.id).first()
        reward = db.query(Reward).filter_by(decision_id=c.id).first()
        results.append({
            "matchday": c.matchday_number,
            "action": c.action_type,
            "bid_amount": c.amount,
            "points_impact": out.points_gained if out else 0.0,
            "wealth_impact": out.wealth_gained if out else 0.0,
            "total_reward": reward.total_reward if reward else 0.0
        })

    return {
        "query_price": price,
        "sample_size": len(results),
        "cases": results
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
                    <span class="badge bg-success py-2 px-3">Modo: Fase 1 Operativo</span>
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
