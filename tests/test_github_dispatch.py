from pathlib import Path

from fastapi.testclient import TestClient

from fantasy_ai_lab.api.main import app
from fantasy_ai_lab.database.connection import get_db
from fantasy_ai_lab.database.models import SimulationJob
from fantasy_ai_lab.integration.github_actions import GitHubActionsClient, GitHubActionsError
from fantasy_ai_lab.simulator.jobs import JobService


def _client_for(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app)


def test_create_job_dispatches_existing_workflow_with_all_inputs(db_session, monkeypatch):
    calls = []

    def fake_dispatch(self, inputs):
        calls.append(dict(inputs))

    monkeypatch.setenv("GITHUB_TOKEN", "test-only-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "ImNacho0/fantasy-ai-lab")
    monkeypatch.setenv("GITHUB_WORKFLOW", "simulate.yml")
    monkeypatch.setenv("GITHUB_REF", "main")
    monkeypatch.setattr(GitHubActionsClient, "dispatch", fake_dispatch)
    client = _client_for(db_session)
    try:
        response = client.post("/api/v1/simulations", json={
            "seed": 321,
            "leagues_total": 4,
            "matchdays": 7,
            "extreme_matchday": 3,
            "extreme_scenario": "STAR_PLAYER_INJURED",
        })
        assert response.status_code == 201
        data = response.json()
        assert data["dispatch"]["accepted"] is True
        assert data["status"] == "pending"
        assert calls == [{
            "job_id": str(data["job_id"]),
            "leagues": "4",
            "matchdays": "7",
            "seed": "321",
            "extreme_matchday": "3",
            "extreme_scenario": "STAR_PLAYER_INJURED",
        }]
        stored = db_session.query(SimulationJob).filter_by(id=data["job_id"]).one()
        assert stored.status == "pending"
        assert stored.configuration["github_dispatch"]["status"] == "accepted"
    finally:
        app.dependency_overrides.clear()


def test_repeated_run_does_not_dispatch_twice_without_explicit_retry(db_session, monkeypatch):
    calls = []

    def fake_dispatch(self, inputs):
        calls.append(inputs)

    monkeypatch.setenv("GITHUB_TOKEN", "test-only-token")
    monkeypatch.setattr(GitHubActionsClient, "dispatch", fake_dispatch)
    client = _client_for(db_session)
    try:
        created = client.post("/api/v1/simulations", json={"seed": 1, "leagues_total": 1, "matchdays": 1})
        job_id = created.json()["job_id"]
        repeated = client.post(f"/api/v1/simulations/{job_id}/run", json={})
        assert repeated.status_code == 200
        assert repeated.json()["accepted"] is False
        assert len(calls) == 1
    finally:
        app.dependency_overrides.clear()


def test_github_rejection_marks_job_failed(db_session, monkeypatch):
    def failing_dispatch(self, inputs):
        raise GitHubActionsError("GitHub rejected workflow dispatch with HTTP 403")

    monkeypatch.setenv("GITHUB_TOKEN", "test-only-token")
    monkeypatch.setattr(GitHubActionsClient, "dispatch", failing_dispatch)
    client = _client_for(db_session)
    try:
        response = client.post("/api/v1/simulations", json={"seed": 2, "leagues_total": 1, "matchdays": 1})
        assert response.status_code == 502
        job = db_session.query(SimulationJob).order_by(SimulationJob.id.desc()).first()
        assert job.status == "failed"
        assert "403" in job.error_message
        assert job.completed_at is not None
        assert "test-only-token" not in response.text
    finally:
        app.dependency_overrides.clear()


def test_simulation_workflow_uses_neon_and_accepts_job_id():
    workflow = Path(".github/workflows/simulate.yml").read_text()
    assert "job_id:" in workflow
    assert "DATABASE_URL: ${{ secrets.DATABASE_URL }}" in workflow
    assert "--job-id" in workflow
    assert "sqlite" not in workflow.lower()


def test_job_status_endpoint_exposes_real_progress_and_error(db_session):
    client = _client_for(db_session)
    try:
        job = JobService.create_job(db_session, seed=9, leagues_total=3, matchdays=5)
        job.status = "running"
        job.leagues_completed = 1
        job.current_matchday_idx = 2
        db_session.commit()
        response = client.get(f"/api/v1/simulations/{job.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert data["progress"] == {
            "leagues_completed": 1,
            "leagues_total": 3,
            "current_league_idx": 0,
            "current_matchday_idx": 2,
        }

        missing = client.get("/api/v1/simulations/999999")
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
