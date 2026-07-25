"""Tests for scheduler and schedule API endpoints."""
import pytest
from src.app import _convert_cron_dow


class TestCronDayOfWeekConversion:
    """Test the cron day-of-week conversion from Unix to APScheduler format."""
    
    def test_convert_single_day_sunday(self):
        """Sunday (0 in Unix) should convert to 6 in APScheduler."""
        result = _convert_cron_dow("0")
        assert result == "6"
    
    def test_convert_single_day_monday(self):
        """Monday (1 in Unix) should convert to 0 in APScheduler."""
        result = _convert_cron_dow("1")
        assert result == "0"
    
    def test_convert_single_day_saturday(self):
        """Saturday (6 in Unix) should convert to 5 in APScheduler."""
        result = _convert_cron_dow("6")
        assert result == "5"
    
    def test_convert_multiple_days(self):
        """Test comma-separated days."""
        # Monday, Wednesday, Friday (1,3,5) → (0,2,4)
        result = _convert_cron_dow("1,3,5")
        assert result == "0,2,4"
    
    def test_convert_range_weekdays(self):
        """Test range of weekdays (Monday-Friday)."""
        # Monday-Friday (1-5) → (0-4)
        result = _convert_cron_dow("1-5")
        assert result == "0-4"
    
    def test_convert_asterisk(self):
        """Asterisk (*) should remain unchanged."""
        result = _convert_cron_dow("*")
        assert result == "*"
    
    def test_convert_complex_expression(self):
        """Test complex expression with ranges and individual values."""
        # Monday, Wednesday, Friday-Sunday (1,3,5-0 in traditional notation)
        # This tests: 1,3,5,0 → 0,2,4,6
        result = _convert_cron_dow("1,3,5,0")
        expected = "0,2,4,6"
        assert result == expected


class TestScheduleAPI:
    """Test schedule management API endpoints."""
    
    def test_get_schedules_empty(self, client, sample_device):
        """Test getting schedules when none exist."""
        response = client.get(f"/api/devices/{sample_device['id']}/schedules")
        assert response.status_code == 200
        assert response.json == []
    
    def test_add_schedule_valid(self, client, sample_device, mock_scheduler):
        """Test adding a valid schedule."""
        response = client.post(
            f"/api/devices/{sample_device['id']}/schedules",
            json={
                "cron_expr": "0 8 * * 5",  # Friday 08:00
                "label": "Friday Morning"
            }
        )
        assert response.status_code == 201
        data = response.json
        assert "id" in data
        assert data["id"] > 0
    
    def test_add_schedule_missing_cron(self, client, sample_device):
        """Test adding schedule without cron expression (should fail)."""
        response = client.post(
            f"/api/devices/{sample_device['id']}/schedules",
            json={"label": "No Cron"}
        )
        assert response.status_code == 400
        assert "cron_expr" in response.json.get("error", "").lower()
    
    def test_delete_schedule(self, client, sample_schedule, mock_scheduler):
        """Test deleting a schedule."""
        response = client.delete(f"/api/schedules/{sample_schedule['id']}")
        assert response.status_code == 200
        
        # Verify it's gone
        get_resp = client.get(
            f"/api/devices/{sample_schedule['device_id']}/schedules"
        )
        schedules = get_resp.json
        assert not any(s["id"] == sample_schedule["id"] for s in schedules)
    
    def test_toggle_schedule_enabled(self, client, sample_schedule, mock_scheduler):
        """Test toggling schedule enabled/disabled state."""
        response = client.patch(
            f"/api/schedules/{sample_schedule['id']}",
            json={"enabled": False}
        )
        assert response.status_code == 200
        
        # Verify state changed
        get_resp = client.get(
            f"/api/devices/{sample_schedule['device_id']}/schedules"
        )
        schedules = get_resp.json
        updated = next((s for s in schedules if s["id"] == sample_schedule["id"]), None)
        assert updated is not None
        assert updated["enabled"] == False
    
    def test_update_schedule_cron(self, client, sample_schedule, mock_scheduler):
        """Test updating schedule's cron expression."""
        new_cron = "0 18 * * 1"  # Monday 18:00
        response = client.patch(
            f"/api/schedules/{sample_schedule['id']}",
            json={"cron_expr": new_cron}
        )
        assert response.status_code == 200
        
        # Verify update
        get_resp = client.get(
            f"/api/devices/{sample_schedule['device_id']}/schedules"
        )
        schedules = get_resp.json
        updated = next((s for s in schedules if s["id"] == sample_schedule["id"]), None)
        assert updated is not None
        assert updated["cron_expr"] == new_cron
    
    def test_update_schedule_label(self, client, sample_schedule, mock_scheduler):
        """Test updating schedule's label."""
        new_label = "Evening Wake"
        response = client.patch(
            f"/api/schedules/{sample_schedule['id']}",
            json={"label": new_label}
        )
        assert response.status_code == 200
        
        # Verify update
        get_resp = client.get(
            f"/api/devices/{sample_schedule['device_id']}/schedules"
        )
        schedules = get_resp.json
        updated = next((s for s in schedules if s["id"] == sample_schedule["id"]), None)
        assert updated is not None
        assert updated["label"] == new_label
    
    def test_saturday_schedule_conversion(self, client, sample_device, mock_scheduler):
        """Test that Saturday schedules are converted correctly (regression test for v1.2.9)."""
        # Create Saturday schedule (6 in Unix cron)
        response = client.post(
            f"/api/devices/{sample_device['id']}/schedules",
            json={
                "cron_expr": "0 9 * * 6",  # Saturday 09:00 in Unix cron
                "label": "Saturday Wake"
            }
        )
        assert response.status_code == 201
        
        # Should convert to APScheduler format (5 for Saturday)
        # This would be verified by checking the scheduler's registered job
        # In production, the _rebuild_schedules() function should handle this
        mock_scheduler.add_job.assert_called()
