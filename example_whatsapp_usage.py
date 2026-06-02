#!/usr/bin/env python3
"""
Example usage of WhatsApp Integration with Marin
This script demonstrates how to use the WhatsApp integration in practice
"""

import sys
import json
sys.path.insert(0, '.')

from tools.whatsapp_integration import tool_whatsapp_manage, whatsapp_integration

def example_usage():
    """Demonstrate practical usage of WhatsApp integration"""
    print("=== WhatsApp Integration Example Usage ===\n")
    
    # Example 1: Process a message from a friend
    print("1. Processing a message from a friend:")
    message_data = json.dumps({
        "sender": "Sarah",
        "content": "Hey! Can you pick up some milk on your way home?",
        "chat_name": "Personal",
        "is_group": False
    })
    result = tool_whatsapp_manage("process", message_data)
    print(f"   {result}\n")
    
    # Example 2: Process a work message
    print("2. Processing a work message:")
    message_data = json.dumps({
        "sender": "Team Lead",
        "content": "Please review the project proposal by end of day",
        "chat_name": "Project Team",
        "is_group": True
    })
    result = tool_whatsapp_manage("process", message_data)
    print(f"   {result}\n")
    
    # Example 3: Process a message with deadline
    print("3. Processing a message with deadline:")
    message_data = json.dumps({
        "sender": "Mom",
        "content": "Don't forget to call grandma tomorrow morning",
        "chat_name": "Family",
        "is_group": False
    })
    result = tool_whatsapp_manage("process", message_data)
    print(f"   {result}\n")
    
    # Example 4: Process an urgent message
    print("4. Processing an urgent message:")
    message_data = json.dumps({
        "sender": "Boss",
        "content": "URGENT: Need the financial report ASAP",
        "chat_name": "Work",
        "is_group": False
    })
    result = tool_whatsapp_manage("process", message_data)
    print(f"   {result}\n")
    
    # Example 5: Check what todos were created
    print("5. Checking todos created from WhatsApp:")
    result = tool_whatsapp_manage("list_todos")
    print(f"   {result}\n")
    
    # Example 6: Get statistics
    print("6. Getting integration statistics:")
    result = tool_whatsapp_manage("stats")
    print(f"   {result}\n")
    
    # Example 7: List recent messages
    print("7. Listing recent messages:")
    result = tool_whatsapp_manage("list_messages")
    print(f"   {result}\n")
    
    print("=== Example Complete ===")
    print("\nIn a real scenario:")
    print("1. WhatsApp messages would be captured automatically by the browser")
    print("2. Each message would be processed for actionable items")
    print("3. Todos would be created automatically")
    print("4. You could check your todos via Marin's chat or web dashboard")
    print("5. The integration tracks which todos came from WhatsApp")

if __name__ == "__main__":
    example_usage()
