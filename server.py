#!/usr/bin/env python3
"""
MCP Server for Marin Games
Exposes game state and move-making capabilities for Tic-Tac-Toe and Connect Four
as MCP tools that return JSON format dictionaries.
"""

import json
import subprocess
import sys
import os
from pathlib import Path
from mcp.server.models import InitializationOptions
import mcp.server.stdio
import mcp.types as types
from mcp.server import NotificationOptions, Server
import mcp.server.stdio

# Base directory for Marin project - hardcoded for reliability
BASE_DIR = Path("/home/sword/Documents/marin")
TOOLS_DIR = BASE_DIR / "tools"

def run_marin_tool(tool_name, args):
    """Run a Marin tool with given arguments and return JSON output."""
    tool_path = TOOLS_DIR / tool_name
    cmd = [sys.executable, str(tool_path)] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # Try to parse as JSON, if fails return as text
            try:
                return json.loads(result.stdout.strip())
            except json.JSONDecodeError:
                return {"output": result.stdout.strip()}
        else:
            return {"error": f"Tool failed: {result.stderr.strip()}"}
    except subprocess.TimeoutExpired:
        return {"error": "Tool execution timed out"}
    except Exception as e:
        return {"error": f"Failed to run tool: {str(e)}"}

# Create the MCP server
server = Server("marin-games")

@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """List available tools."""
    return [
        types.Tool(
            name="get_tictactoe_state",
            description="Get the current state of the Tic-Tac-Toe game as a JSON dictionary",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="make_tictactoe_move",
            description="Make a move in Tic-Tac-Toe at position 0-8 and get the new state",
            inputSchema={
                "type": "object",
                "properties": {
                    "position": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 8,
                        "description": "Position on the board (0-8, top-left to bottom-right)"
                    }
                },
                "required": ["position"]
            }
        ),
        types.Tool(
            name="get_connect4_state",
            description="Get the current state of the Connect Four game as a JSON dictionary",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        ),
        types.Tool(
            name="make_connect4_move",
            description="Make a move in Connect Four in column 0-6 and get the new state",
            inputSchema={
                "type": "object",
                "properties": {
                    "column": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 6,
                        "description": "Column to drop the piece (0-6, left to right)"
                    }
                },
                "required": ["column"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool calls."""
    if name == "get_tictactoe_state":
        result = run_marin_tool("tictactoe.py", ["--get-state"])
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "make_tictactoe_move":
        position = arguments.get("position")
        if position is None:
            result = {"error": "Missing 'position' argument"}
        else:
            result = run_marin_tool("tictactoe.py", ["--move", str(position)])
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "get_connect4_state":
        result = run_marin_tool("connect4.py", ["--get-state"])
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    elif name == "make_connect4_move":
        column = arguments.get("column")
        if column is None:
            result = {"error": "Missing 'column' argument"}
        else:
            result = run_marin_tool("connect4.py", ["--move", str(column)])
        return [types.TextContent(
            type="text",
            text=json.dumps(result, indent=2)
        )]
    
    else:
        return [types.TextContent(
            type="text",
            text=json.dumps({"error": f"Unknown tool: {name}"})
        )]

async def main():
    # Run the server using stdin/stdout
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="marin-games",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())