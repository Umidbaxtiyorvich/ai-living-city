from fastapi.testclient import TestClient

from app.main import app


def test_health_and_snapshot_contain_a_living_city():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200
        assert health.json()["ok"] is True

        snap = client.get("/api/snapshot")
        assert snap.status_code == 200
        body = snap.json()
        assert body["kind"] == "snapshot"
        assert body["tiles"]["width"] >= 60
        assert len(body["agents"]) >= 20
        assert body["president"]["name"]
        assert body["dashboard"]["stats"]["population"] >= 20
        assert len(body["buildings"]) >= 8


def test_speed_and_follow_endpoints():
    with TestClient(app) as client:
        paused = client.post("/api/speed", json={"value": 0})
        assert paused.status_code == 200
        assert paused.json()["speed"] == 0

        bad = client.post("/api/speed", json={"value": 7})
        assert bad.status_code == 400

        follow = client.post("/api/follow", json={"target": "president"})
        assert follow.status_code == 200
        assert follow.json()["follow_president"] is True


def test_player_can_decree_and_switch_role():
    with TestClient(app) as client:
        snap = client.get("/api/snapshot").json()
        assert snap["president"]["name"] == "Umid Ravshanov"
        assert snap["dashboard"]["player"]["role"] == "president"

        built = client.post("/api/command", json={"text": "1 ta uy qur"})
        assert built.status_code == 200
        body = built.json()
        assert body["ok"] is True
        assert "qurilishi" in body["reply"] or "yetmayapti" in body["reply"]

        role = client.post("/api/role", json={"role": "prime_minister"})
        assert role.status_code == 200
        assert role.json()["player"]["role"] == "prime_minister"

        queued = client.post("/api/command", json={"text": "2 ta uy qur"})
        assert queued.status_code == 200
        assert queued.json()["ok"] is True
        assert queued.json()["player"]["decrees"]


def test_the_city_survives_a_server_restart():
    """Specification section 39: the civilization continues after a restart."""
    with TestClient(app) as client:
        client.post("/api/speed", json={"value": 0})
        saved = client.post("/api/save")
        assert saved.status_code == 200
        body = saved.json()
        assert body["saved"] is True

        before = client.get("/api/snapshot").json()

    # A fresh process would build a new Runtime; the fixture keeps the same
    # database, so startup must find the save and continue that city.
    with TestClient(app) as client:
        after = client.get("/api/snapshot").json()

        assert after["president"]["name"] == before["president"]["name"]
        assert after["dashboard"]["time"]["tick"] >= before["dashboard"]["time"]["tick"]
        assert len(after["agents"]) == len(before["agents"])

        history = client.get("/api/history").json()
        assert history["metrics"], "no daily metrics were recorded"
