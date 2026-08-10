from fastapi.testclient import TestClient

from fantasy_ai_lab.api.main import app
from fantasy_ai_lab.integration.fantasy_manager import FantasyManagerAdapter

client = TestClient(app)


def test_phase6_integration_status_is_read_only():
    response = client.get("/api/v1/integration/fantasy-manager/status")
    assert response.status_code == 200
    data = response.json()
    assert data["mode"] == "read-only"
    assert data["execution"]["allowed"] is False


def test_phase6_adapter_normalizes_snapshot_without_execution(db_session):
    result = FantasyManagerAdapter.recommend(db_session, {
        "leagueState": {"matchday": 12},
        "market": {"liquidity": "high"},
        "team": {"budget": 12000000, "roster": []},
        "context": {"player": {"id": "p-1", "price": 7000000, "status": "healthy"}},
    })
    assert result["mode"] == "read-only"
    assert result["playerId"] == "p-1"
    assert result["execution"]["allowed"] is False
    assert result["features"]["matchday"] == 12


def test_phase6_integration_endpoint_returns_evidence_contract():
    response = client.post("/api/v1/integration/fantasy-manager/decision", json={
        "leagueState": {"matchday": 4},
        "market": {},
        "team": {"budget": 10000000, "roster": []},
        "lineup": {},
        "context": {"player": {"id": "p-2", "price": 5000000}},
    })
    assert response.status_code == 200
    data = response.json()
    assert data["recommendedAction"] == "HOLD"
    assert data["sampleSize"] == 0
    assert data["execution"]["allowed"] is False
