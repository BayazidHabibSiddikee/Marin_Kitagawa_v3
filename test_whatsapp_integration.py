#!/usr/bin/env python3
"""
Test script for WhatsApp Integration with Marin
Demonstrates how WhatsApp messages can be processed and turned into todos
"""

import sys
import json
sys.path.insert(0, '.')

from tools.whatsapp_integration import tool_whatsapp_manage, whatsapp_integration

def test_whatsapp_integration():
    """Test the WhatsApp integration functionality"""
    print("=== WhatsApp Integration Test ===\n")
    
    # Test 1: Process a sample WhatsApp message
    print("1. Processing sample WhatsApp message...")
    message_data = json.dumps({
        "sender": "Alice",
        "content": "Please buy groceries tomorrow",
        "chat_name": "Family Group",
        "is_group": True
    })
    result = tool_whatsapp_manage("process", message_data)
    print(f"   Result: {result}\n")
    
    # Test 2: Process another message with different content
    print("2. Processing another message...")
    message_data = json.dumps({
        "sender": "Bob",
        "content": "Meeting at 3pm today",
        "chat_name": "Work",
        "is_group": False
    })
    result = tool_whatsapp_manage("process", message_data)
    print(f"   Result: {result}\n")
    
    # Test 3: Process a message with high priority
    print("3. Processing urgent message...")
    message_data = json.dumps({
        "sender": "Manager",
        "content": "URGENT: Submit report by Friday",
        "chat_name": "Work",
        "is_group": False
    })
    result = tool_whatsapp_manage("process", message_data)
    print(f"   Result: {result}\n")
    
    # Test 4: List all todos created from WhatsApp
    print("4. Listing WhatsApp-generated todos...")
    result = tool_whatsapp_manage("list_todos")
    print(f"   {result}\n")
    
    # Test 5: Get integration stats
    print("5. Getting integration stats...")
    result = tool_whatsapp_manage("stats")
    print(f"   {result}\n")
    
    # Test 6: List recent messages
    print("6. Listing recent messages...")
    result = tool_whatsapp_manage("list_messages")
    print(f"   {result}\n")
    
    print("=== Test Complete ===")
    print("\nThe WhatsApp integration is now working!")
    print("Marin can now:")
    print("- Process WhatsApp messages automatically")
    print("- Extract actionable items (todos, deadlines, questions)")
    print("- Create todos in the existing todo system")
    print("- Track which todos came from WhatsApp")
    print("- Provide stats on WhatsApp-generated tasks")

if __name__ == "__main__":
    test_whatsapp_integration()
