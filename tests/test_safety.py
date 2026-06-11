import pytest
from safety import KillSwitch, agent_needs_confirmation

def test_kill_switch_blocking():
    """Verify that kill switch blocks commands when active."""
    ks = KillSwitch()
    
    # 1. Deactivate (default)
    ks.deactivate()
    assert ks.check() == True
    
    # 2. Activate
    ks.activate("test")
    assert ks.check() == False
    
    # 3. Cleanup
    ks.deactivate()

def test_hitl_confirmation():
    """Verify that sensitive actions require confirmation."""
    # marin agent has no requires-confirm actions, so all return False
    assert agent_needs_confirmation("marin", "terminal_tool") == False
    # system agent has restart_service
    assert agent_needs_confirmation("system", "restart_service") == True
    assert agent_needs_confirmation("system", "weather_tool") == False
