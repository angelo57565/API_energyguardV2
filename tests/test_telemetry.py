from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from app import database, main, services
from app.config import get_settings
from app.routers import readings


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    sessions = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(database, "engine", engine)
    monkeypatch.setattr(main, "engine", engine)
    monkeypatch.setattr(database, "SessionLocal", sessions)
    monkeypatch.setattr(services, "SessionLocal", sessions)
    settings = get_settings()
    monkeypatch.setattr(settings, "api_key", "dashboard")
    monkeypatch.setattr(settings, "ingest_api_key", "esp32")
    monkeypatch.setattr(settings, "require_api_keys", True)
    monkeypatch.setattr(settings, "model_path", str(tmp_path / "model.joblib"))
    monkeypatch.setattr(settings, "min_train_samples", 200)
    monkeypatch.setattr(services.detector, "_model", None)
    monkeypatch.setattr(services.detector, "_meta", {})
    with TestClient(main.app, headers={"X-API-Key": "dashboard"}) as client:
        yield client
    engine.dispose()


def sample(energy, seconds_ago, device="esp32-01", frequency=60):
    return {
        "device_id": device, "voltage": 127, "current": 1, "power": 127,
        "energy": energy, "frequency": frequency, "power_factor": 1,
        "measured_ts": int(datetime.now(timezone.utc).timestamp()) - seconds_ago,
    }


def upload(api, *samples):
    return api.post("/api/readings/batch", json={"readings": samples}, headers={"X-API-Key": "esp32"})


def test_consumption_per_device_with_reset_and_delayed_readings(api):
    assert upload(api, sample(0.5, 10), sample(501, 20, "b")).status_code == 201
    assert upload(
        api, sample(100, 40), sample(101, 30), sample(500, 40, "b"),
    ).json()["stored"] == 3
    assert api.get("/api/summary").json()["energy_kwh"] == 2.5
    assert api.get("/api/summary?device_id=b").json()["energy_kwh"] == 1
    assert sum(row["kwh"] for row in api.get("/api/consumption/hourly").json()) == 2.5
    assert api.get("/api/readings/latest?device_id=esp32-01").json()["energy"] == 0.5
    assert [row["energy"] for row in api.get("/api/readings?device_id=esp32-01").json()] == [
        100, 101, 0.5,
    ]


def test_concurrent_replay(api):
    reading = sample(1, 10)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(upload, api, reading) for _ in range(2)]
        results = [future.result().json() for future in futures]
    assert sorted(result["stored"] for result in results) == [0, 1]
    assert sorted(result["duplicates"] for result in results) == [0, 1]


def test_last_seen_uses_receipt_and_invalid_epoch_is_accepted(api):
    assert upload(api, sample(1, 3600)).status_code == 201
    reading = api.get("/api/readings/latest").json()
    device = api.get("/api/devices").json()[0]
    assert device["last_seen"] > reading["created_at"]
    services.check_offline()
    assert api.get("/api/alerts/events").json() == []

    invalid_epoch = {**sample(2, 0), "measured_ts": 10**30}
    assert upload(api, invalid_epoch, invalid_epoch).json()["stored"] == 2


def test_batch_rolls_back_readings_and_alerts(api, monkeypatch):
    rule = {"name": "Tensão", "metric": "voltage", "operator": ">", "threshold": 120}
    assert api.post("/api/alerts/rules", json=rule).status_code == 201
    evaluate = readings.evaluate_alerts

    def fail_second(db, reading):
        if reading.energy == 2:
            raise RuntimeError("falha antes do commit")
        return evaluate(db, reading)

    with monkeypatch.context() as patch:
        patch.setattr(readings, "evaluate_alerts", fail_second)
        with pytest.raises(RuntimeError, match="falha antes do commit"):
            upload(api, sample(1, 20), sample(2, 10))
    assert api.get("/api/readings").json() == []
    assert api.get("/api/alerts/events").json() == []
    assert upload(api, sample(1, 20), sample(2, 10)).json()["stored"] == 2
    assert len(api.get("/api/alerts/events").json()) == 1


def test_credentials_and_quality(api):
    assert api.get("/api/summary", headers={"X-API-Key": "esp32"}).status_code == 401
    assert api.post("/api/readings", json=sample(1, 10)).status_code == 401
    assert upload(api, sample(1, 20, frequency=0), sample(2, 10, frequency=58)).status_code == 201
    assert api.get("/api/quality").json()["frequency"]["out_pct"] == 100
    assert api.get("/api/quality?vmin=133&vmax=117").status_code == 422


def test_retraining_after_batch_crosses_interval(api, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "min_train_samples", 2)
    monkeypatch.setattr(settings, "retrain_every", 2)
    monkeypatch.setattr(settings, "n_estimators", 2)
    assert upload(api, sample(1, 50), sample(2, 40)).status_code == 201
    assert api.get("/api/model/status").json()["readings_at_train"] == 2
    assert upload(api, sample(3, 30), sample(4, 20), sample(5, 10)).status_code == 201
    assert api.get("/api/model/status").json()["readings_at_train"] == 5


def test_legacy_schema_migration_retains_rows(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    monkeypatch.setattr(database, "engine", engine)
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE readings (id INTEGER PRIMARY KEY, device_id VARCHAR(64), created_at DATETIME)"
        )
        conn.exec_driver_sql("INSERT INTO readings (id, device_id) VALUES (1, 'esp32-01')")
    database.migrate()
    database.migrate()
    with engine.connect() as conn:
        assert conn.execute(select(database.Base.metadata.tables["readings"].c.id)).scalar_one() == 1
    assert any(
        index["name"] == "ux_readings_device_measured" and index["unique"]
        for index in inspect(engine).get_indexes("readings")
    )
    engine.dispose()
