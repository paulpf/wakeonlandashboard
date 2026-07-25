"""Pytest fixtures for WoL Dashboard tests."""
import os
import pytest
from unittest.mock import MagicMock, patch

# Import app and database modules
from app import app as flask_app
import database as db


@pytest.fixture(autouse=True)
def reset_database():
    """Reset database before each test."""
    # Clear all data from tables
    with db.get_db() as conn:
        conn.execute("DELETE FROM devices")
        conn.execute("DELETE FROM schedules")
        conn.execute("DELETE FROM wake_history")
        conn.execute("DELETE FROM scan_results")
        conn.commit()
    
    yield
    
    # Cleanup after test
    with db.get_db() as conn:
        conn.execute("DELETE FROM devices")
        conn.execute("DELETE FROM schedules")
        conn.execute("DELETE FROM wake_history")
        conn.execute("DELETE FROM scan_results")
        conn.commit()


@pytest.fixture
def client():
    """Create a Flask test client."""
    flask_app.config["TESTING"] = True
    
    with flask_app.test_client() as test_client:
        yield test_client


@pytest.fixture
def sample_device():
    """Insert a sample device in the test database."""
    from database import upsert_device
    
    dev_id = upsert_device(
        name="TestPC",
        mac="00:11:22:33:44:55",
        ip="192.168.1.100",
        broadcast="192.168.1.255",
        group_name="TestGroup",
        notes="Test device",
        port_checks=[],
    )
    return {
        "id": dev_id,
        "name": "TestPC",
        "mac": "00:11:22:33:44:55",
        "ip": "192.168.1.100",
    }


@pytest.fixture
def sample_schedule(sample_device):
    """Insert a sample schedule for testing."""
    from database import add_schedule
    
    sched_id = add_schedule(
        device_id=sample_device["id"],
        cron_expr="0 8 * * 5",  # Friday 08:00
        label="Morning wake"
    )
    return {
        "id": sched_id,
        "device_id": sample_device["id"],
        "cron_expr": "0 8 * * 5",
    }


@pytest.fixture
def mock_scanner(monkeypatch):
    """Mock scanner functions to prevent actual network calls."""
    mock = MagicMock()
    mock.check_device_online.return_value = False
    mock.scan_network.return_value = []
    mock.scan_ports_bulk.return_value = {}
    mock.scan_ports_for_ip.return_value = []
    
    monkeypatch.setattr("app.scanner", mock)
    return mock


@pytest.fixture
def mock_wol(monkeypatch):
    """Mock WoL send_magic_packet to prevent actual network calls."""
    mock = MagicMock()
    
    monkeypatch.setattr("app.wol_mod.send_magic_packet", mock)
    return mock


@pytest.fixture
def mock_scheduler(monkeypatch):
    """Mock APScheduler to prevent actual job scheduling."""
    from apscheduler.schedulers.background import BackgroundScheduler
    
    mock_sched = MagicMock(spec=BackgroundScheduler)
    mock_sched.get_jobs.return_value = []
    mock_sched.add_job.return_value = None
    mock_sched.get_job.return_value = None
    
    # Patch the global scheduler in app
    monkeypatch.setattr("app.scheduler", mock_sched)
    return mock_sched
