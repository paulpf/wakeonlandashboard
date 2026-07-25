"""Tests for device API endpoints."""
import pytest
import json


def test_get_devices_empty(client):
    """Test getting devices when none exist."""
    response = client.get("/api/devices")
    assert response.status_code == 200
    assert response.json == []


def test_get_devices_with_sample(client, sample_device):
    """Test getting devices after adding one."""
    response = client.get("/api/devices")
    assert response.status_code == 200
    devices = response.json
    assert len(devices) >= 1
    assert any(d["mac"] == "00:11:22:33:44:55" for d in devices)


def test_add_device_valid(client):
    """Test adding a device with valid data."""
    response = client.post(
        "/api/devices",
        json={
            "name": "NewPC",
            "mac": "AA:BB:CC:DD:EE:FF",
            "ip": "192.168.1.50",
            "group_name": "Work",
        }
    )
    assert response.status_code == 201
    data = response.json
    assert "id" in data
    assert data["id"] > 0


def test_add_device_missing_mac(client):
    """Test adding device without MAC (should fail)."""
    response = client.post(
        "/api/devices",
        json={
            "name": "NewPC",
            "ip": "192.168.1.50",
        }
    )
    assert response.status_code == 400
    assert "mac" in response.json.get("error", "").lower()


def test_add_device_missing_name(client):
    """Test adding device without name (should fail)."""
    response = client.post(
        "/api/devices",
        json={
            "mac": "AA:BB:CC:DD:EE:FF",
            "ip": "192.168.1.50",
        }
    )
    assert response.status_code == 400
    assert "name" in response.json.get("error", "").lower()


def test_update_device(client, sample_device):
    """Test updating device properties."""
    new_name = "UpdatedPC"
    response = client.put(
        f"/api/devices/{sample_device['id']}",
        json={
            "name": new_name,
            "notes": "Updated notes",
        }
    )
    assert response.status_code == 200
    
    # Verify update
    get_resp = client.get("/api/devices")
    devices = get_resp.json
    updated = next((d for d in devices if d["id"] == sample_device["id"]), None)
    assert updated is not None
    assert updated["name"] == new_name
    assert updated["notes"] == "Updated notes"


def test_update_nonexistent_device(client):
    """Test updating a device that doesn't exist."""
    response = client.put(
        "/api/devices/99999",
        json={"name": "Ghost"}
    )
    assert response.status_code == 404


def test_delete_device(client, sample_device):
    """Test deleting a device."""
    device_id = sample_device["id"]
    
    # Delete
    response = client.delete(f"/api/devices/{device_id}")
    assert response.status_code == 200
    
    # Verify deletion
    get_resp = client.get("/api/devices")
    devices = get_resp.json
    assert not any(d["id"] == device_id for d in devices)
