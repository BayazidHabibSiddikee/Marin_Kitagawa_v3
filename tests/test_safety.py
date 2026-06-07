import pytest
from safety import KillSwitch, agent_needs_confirmation

def test_kill_switch_blocking():
    """Verify that kill switch blocks commands when active."""
    ks = KillSwitch()
    
    # 1. Deactivate (default)
    ks.is_active = False
    assert ks.check() == True
    
    # 2. Activate
    ks.is_active = True
    assert ks.check() == False

def test_hitl_confirmation():
    """Verify that sensitive actions require confirmation."""
    # This should be True if not in docker
    import os
    os.environ["DOCKER_CONTAINER"] = "" # Force host mode for test
    assert agent_needs_confirmation("marin", "terminal_tool") == True
    assert agent_needs_confirmation("marin", "weather_tool") == False
