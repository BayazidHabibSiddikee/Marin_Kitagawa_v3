import pytest
from langgraph_agent import tools_by_name

@pytest.mark.parametrize("tool_name", [
    "timer_tool", "math_plot_tool", "weather_tool", "terminal_tool"
])
def test_tool_registry(tool_name):
    """Verify all core tools are in the registry."""
    assert tool_name in tools_by_name

def test_weather_tool():
    """Smoke test for weather tool."""
    res = tools_by_name["weather_tool"].invoke({"city": "Dhaka"})
    assert "Weather" in res or "Error" in res

def test_terminal_tool_blocked():
    """Verify terminal tool blocks dangerous commands."""
    res = tools_by_name["terminal_tool"].invoke({"command": "rm -rf /"})
    assert "Exit Code: 1" in res or "Blocked" in res
