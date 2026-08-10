from fastapi.testclient import TestClient
from fantasy_ai_lab.api.main import app

client = TestClient(app)

def test_api_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_api_event_catalog():
    response = client.get("/api/v1/events/catalog")
    assert response.status_code == 200
    catalog = response.json()["events"]
    assert catalog["STAR_PLAYER_INJURED"]["is_extreme"] is True
    assert "uncertainty" in catalog["MARKET_CRASH"]


def test_api_create_job():
    response = client.post(
        "/api/v1/simulations",
        json={"seed": 111, "leagues_total": 2, "matchdays": 3}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
    assert data["leagues_total"] == 2
    assert data["matchdays"] == 3

def test_api_list_jobs():
    response = client.get("/api/v1/simulations")
    assert response.status_code == 200
    assert isinstance(response.json(), list)

def test_api_decision_recommendation():
    # Call the decision integration endpoint
    payload = {
        "leagueState": {},
        "market": {},
        "team": {},
        "lineup": {},
        "context": {
            "playerId": "p_99",
            "playerName": "Lionel Test",
            "playerPrice": 8500000.0
        }
    }
    response = client.post("/api/v1/decision", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "recommendedAction" in data
    assert data["playerId"] == "p_99"
    assert "confidence" in data
    assert "explanation" in data
