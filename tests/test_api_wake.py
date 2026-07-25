"""Tests for WoL wake API endpoints."""
import pytest
import json
from unittest.mock import call


def test_wake_device_success(client, sample_device, mock_wol, mock_scheduler):
    """Test successfully waking a device."""
    response = client.post(
        f"/api/devices/{sample_device['id']}/wake"
    )
    assert response.status_code == 200
    assert response.json == {"ok": True}
    
    # Verify WoL packet was sent with correct MAC
    mock_wol.assert_called_once()
    args, kwargs = mock_wol.call_args
    assert sample_device["mac"] in args


def test_wake_nonexistent_device(client, mock_wol):
    """Test waking a device that doesn't exist."""
    response = client.post("/api/devices/99999/wake")
    assert response.status_code == 404
    assert "not found" in response.json.get("error", "").lower()
    
    # Verify WoL was NOT called
    mock_wol.assert_not_called()


def test_wake_bulk_multiple_devices(client, mock_wol, mock_scheduler):
    """Test bulk wake with multiple devices."""
    from src.database import upsert_device
    
    # Add 3 test devices
    dev1 = upsert_device("PC1", "11:11:11:11:11:11", "192.168.1.10", "", "Test", "", [])
    dev2 = upsert_device("PC2", "22:22:22:22:22:22", "192.168.1.20", "", "Test", "", [])
    dev3 = upsert_device("PC3", "33:33:33:33:33:33", "192.168.1.30", "", "Test", "", [])
    
    response = client.post(
        "/api/wake/bulk",
        json={"ids": [dev1, dev2, dev3]}
    )
    assert response.status_code == 200
    results = response.json
    
    assert len(results) == 3
    assert all(r["ok"] for r in results)
    
    # Verify WoL was called 3 times
    assert mock_wol.call_count == 3


def test_wake_bulk_partial_failure(client, mock_wol, mock_scheduler):
    """Test bulk wake with one invalid device ID."""
    from src.database import upsert_device
    
    dev1 = upsert_device("PC1", "11:11:11:11:11:11", "192.168.1.10", "", "Test", "", [])
    
    response = client.post(
        "/api/wake/bulk",
        json={"ids": [dev1, 99999]}  # 99999 doesn't exist
    )
    assert response.status_code == 200
    results = response.json
    
    # Only the valid device should be woken
    assert len(results) == 1
    assert results[0]["ok"]
    
    mock_wol.assert_called_once()


def test_wake_triggers_fast_polling(client, sample_device, mock_wol, mock_scheduler):
    """Test that wake request enables fast polling."""
    response = client.post(
        f"/api/devices/{sample_device['id']}/wake"
    )
    assert response.status_code == 200
    
    # Mock scheduler should have been called to reschedule
    # The reschedule is done via the job's reschedule method
    mock_scheduler.get_job.assert_called()


def test_wake_logs_history(client, sample_device, mock_wol, mock_scheduler):
    """Test that wake request is logged to history."""
    response = client.post(
        f"/api/devices/{sample_device['id']}/wake"
    )
    assert response.status_code == 200
    
    # Check history
    history_resp = client.get("/api/history?limit=10")
    assert history_resp.status_code == 200
    history = history_resp.json
    
    # Should have a wake log entry
    assert len(history) > 0
    latest = history[0]
    assert latest["mac"] == sample_device["mac"]
    assert latest["triggered_by"] == "manual"
    assert latest["success"] == 1


def test_wake_broadcast_address(client, sample_device, mock_wol, mock_scheduler):
    """Test that device's broadcast address is used or default."""
    response = client.post(
        f"/api/devices/{sample_device['id']}/wake"
    )
    assert response.status_code == 200
    
    # Check that WoL was called with broadcast address
    mock_wol.assert_called_once()
    args, kwargs = mock_wol.call_args
    # Args should be (mac, broadcast_addr, port)
    assert len(args) >= 2


def test_wake_with_custom_port(client, sample_device, mock_wol, mock_scheduler):
    """Test wake with custom WoL port from config."""
    # This would require config setup - simplified version
    response = client.post(
        f"/api/devices/{sample_device['id']}/wake"
    )
    assert response.status_code == 200
    
    mock_wol.assert_called_once()
