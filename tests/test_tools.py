import pytest
from langgraph_agent import tools_by_name

@pytest.mark.parametrize("tool_name", [
    "alarm_tool", "timer_tool", "math_plot_tool", "news_tool", 
    "weather_tool", "stock_tool", "crypto_tool", "terminal_tool"
])
def test_tool_registry(tool_name):
    """Verify all core tools are in the registry."""
    assert tool_name in tools_by_name

def test_weather_tool():
    """Smoke test for weather tool."""
    res = tools_by_name["weather_tool"].invoke({"city": "Dhaka"})
    assert "Weather" in res or "Error" in res

def test_crypto_tool():
    """Smoke test for crypto tool."""
    res = tools_by_name["crypto_tool"].invoke({"coin": "bitcoin"})
    assert "bitcoin" in res.lower() or "price" in res.lower() or "Error" in res

def test_terminal_tool_blocked():
    """Verify terminal tool blocks dangerous commands."""
    res = tools_by_name["terminal_tool"].invoke({"command": "rm -rf /"})
    assert "Blocked" in res
