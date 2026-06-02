"""
WhatsApp Integration Tool for Marin
Monitors WhatsApp messages and extracts actionable items for todo creation
"""

import asyncio
import json
import re
import sqlite3
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("WhatsAppIntegration")

@dataclass
class WhatsAppMessage:
    sender: str
    content: str
    timestamp: datetime
    chat_name: str
    is_group: bool = False
    message_id: Optional[str] = None

@dataclass
class ActionableItem:
    message: WhatsAppMessage
    action_type: str  # 'todo', 'reminder', 'deadline', 'question', 'info'
    priority: str  # 'high', 'medium', 'low'
    extracted_text: str
    confidence: float

class WhatsAppMessageParser:
    """Parse WhatsApp messages to extract actionable items"""
    
    # Patterns for detecting actionable items
    TODO_PATTERNS = [
        r'(?i)(?:todo|task|do|complete|finish|complete|finish|complete)\s*[:\-]?\s*(.+)',
        r'(?i)(?:need to|have to|must|should)\s+(.+)',
        r'(?i)(?:please|plz|pls)\s+(.+)',
        r'(?i)(?:remember|remind me|don\'t forget)\s+(.+)',
        r'(?i)(?:buy|get|pick up|fetch|bring)\s+(.+)',
        r'(?i)(?:call|text|message|email|contact)\s+(.+)',
        r'(?i)(?:schedule|set up|arrange|organize)\s+(.+)',
        r'(?i)(?:submit|send|deliver|hand in)\s+(.+)',
    ]
    
    DEADLINE_PATTERNS = [
        r'(?i)(?:by|before|due|deadline|until)\s+(?:tomorrow|today|next week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{1,2}(?:st|nd|rd|th)?(?:\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*)?)',
        r'(?i)(?:due|deadline)\s+(?:on|at)\s+(.+)',
    ]
    
    QUESTION_PATTERNS = [
        r'(?i)(?:what|when|where|who|why|how|can you|could you|would you)\s+(.+)\??',
        r'(?i)(?:do you know|any idea|wondering|curious)\s+(.+)',
    ]
    
    def __init__(self):
        self.high_priority_keywords = ['urgent', 'asap', 'emergency', 'important', 'critical', 'now']
        self.medium_priority_keywords = ['soon', 'today', 'this week', 'priority']
        self.low_priority_keywords = ['whenever', 'sometime', 'later', 'no rush']
    
    def parse_message(self, message: WhatsAppMessage) -> List[ActionableItem]:
        """Parse a WhatsApp message and extract actionable items"""
        items = []
        text = message.content.strip()
        
        if not text or len(text) < 5:
            return items
        
        # Check for todo patterns
        for pattern in self.TODO_PATTERNS:
            match = re.search(pattern, text)
            if match:
                extracted = match.group(1).strip()
                priority = self._determine_priority(text)
                items.append(ActionableItem(
                    message=message,
                    action_type='todo',
                    priority=priority,
                    extracted_text=extracted,
                    confidence=0.8
                ))
                break
        
        # Check for deadline patterns
        for pattern in self.DEADLINE_PATTERNS:
            match = re.search(pattern, text)
            if match:
                priority = self._determine_priority(text)
                items.append(ActionableItem(
                    message=message,
                    action_type='deadline',
                    priority=priority,
                    extracted_text=text,
                    confidence=0.7
                ))
                break
        
        # Check for question patterns
        for pattern in self.QUESTION_PATTERNS:
            match = re.search(pattern, text)
            if match:
                items.append(ActionableItem(
                    message=message,
                    action_type='question',
                    priority='medium',
                    extracted_text=text,
                    confidence=0.6
                ))
                break
        
        # If no specific patterns match, check if it looks like a task
        if not items and self._looks_like_task(text):
            priority = self._determine_priority(text)
            items.append(ActionableItem(
                message=message,
                action_type='todo',
                priority=priority,
                extracted_text=text,
                confidence=0.5
            ))
        
        return items
    
    def _determine_priority(self, text: str) -> str:
        """Determine priority based on keywords"""
        text_lower = text.lower()
        
        for keyword in self.high_priority_keywords:
            if keyword in text_lower:
                return 'high'
        
        for keyword in self.medium_priority_keywords:
            if keyword in text_lower:
                return 'medium'
        
        for keyword in self.low_priority_keywords:
            if keyword in text_lower:
                return 'low'
        
        return 'medium'
    
    def _looks_like_task(self, text: str) -> bool:
        """Heuristic to check if text looks like a task"""
        task_indicators = [
            'need', 'must', 'should', 'have to', 'required',
            'please', 'plz', 'pls', 'kindly', 'request',
            'submit', 'send', 'complete', 'finish', 'do'
        ]
        
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in task_indicators)

class WhatsAppTodoManager:
    """Manage todos created from WhatsApp messages"""
    
    def __init__(self, db_path: str = "storage/todos.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize the todo database"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create whatsapp_todos table for tracking source
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS whatsapp_todos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                todo_id INTEGER NOT NULL,
                sender TEXT NOT NULL,
                chat_name TEXT,
                original_message TEXT,
                extracted_text TEXT,
                confidence REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (todo_id) REFERENCES todos(id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_todo_from_actionable_item(self, item: ActionableItem) -> int:
        """Create a todo from an actionable item"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create the todo
        cursor.execute(
            "INSERT INTO todos (title, priority, status) VALUES (?, ?, ?)",
            (item.extracted_text, item.priority, 'todo')
        )
        todo_id = cursor.lastrowid
        
        # Track the WhatsApp source
        cursor.execute(
            "INSERT INTO whatsapp_todos (todo_id, sender, chat_name, original_message, extracted_text, confidence) VALUES (?, ?, ?, ?, ?, ?)",
            (todo_id, item.message.sender, item.message.chat_name, item.message.content, item.extracted_text, item.confidence)
        )
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created todo #{todo_id} from WhatsApp message by {item.message.sender}")
        return todo_id
    
    def get_whatsapp_todos(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Get todos that came from WhatsApp messages"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT t.*, wt.sender, wt.chat_name, wt.original_message, wt.confidence, wt.created_at as whatsapp_created_at
            FROM todos t
            JOIN whatsapp_todos wt ON t.id = wt.todo_id
            ORDER BY wt.created_at DESC
            LIMIT ?
        ''', (limit,))
        
        todos = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        return todos
    
    def get_whatsapp_stats(self) -> Dict[str, Any]:
        """Get statistics about WhatsApp-generated todos"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN t.status='todo' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN t.status='done' THEN 1 ELSE 0 END) as completed,
                AVG(wt.confidence) as avg_confidence
            FROM todos t
            JOIN whatsapp_todos wt ON t.id = wt.todo_id
        ''')
        
        row = cursor.fetchone()
        if row:
            stats = dict(row)
        else:
            stats = {"total": 0, "pending": 0, "completed": 0, "avg_confidence": 0}
        conn.close()
        
        return stats

class WhatsAppIntegration:
    """Main WhatsApp integration class"""
    
    def __init__(self):
        self.parser = WhatsAppMessageParser()
        self.todo_manager = WhatsAppTodoManager()
        self.messages: List[WhatsAppMessage] = []
        self.actionable_items: List[ActionableItem] = []
        self.notification_callbacks: List[callable] = []
    
    def register_notification_callback(self, callback: callable):
        """Register a callback function to be called when new messages arrive"""
        self.notification_callbacks.append(callback)
    
    async def _send_notifications(self, message: WhatsAppMessage, items: List[ActionableItem]):
        """Send notifications for new messages"""
        for callback in self.notification_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(message, items)
                else:
                    callback(message, items)
            except Exception as e:
                logger.error(f"Notification callback error: {e}")
    
    async def process_whatsapp_message(self, sender: str, content: str, chat_name: str = "Unknown", is_group: bool = False) -> List[ActionableItem]:
        """Process a WhatsApp message and extract actionable items"""
        message = WhatsAppMessage(
            sender=sender,
            content=content,
            timestamp=datetime.now(),
            chat_name=chat_name,
            is_group=is_group
        )
        
        self.messages.append(message)
        
        # Parse for actionable items
        items = self.parser.parse_message(message)
        self.actionable_items.extend(items)
        
        # Create todos from high-confidence items
        created_todos = []
        for item in items:
            if item.confidence >= 0.7:  # Only create todos for high-confidence items
                todo_id = self.todo_manager.create_todo_from_actionable_item(item)
                created_todos.append((todo_id, item))
        
        # Send notifications
        await self._send_notifications(message, items)
        
        return items
    
    def get_recent_messages(self, limit: int = 50) -> List[WhatsAppMessage]:
        """Get recent WhatsApp messages"""
        return self.messages[-limit:]
    
    def get_actionable_items(self, min_confidence: float = 0.5) -> List[ActionableItem]:
        """Get actionable items above confidence threshold"""
        return [item for item in self.actionable_items if item.confidence >= min_confidence]
    
    def get_integration_stats(self) -> Dict[str, Any]:
        """Get integration statistics"""
        todo_stats = self.todo_manager.get_whatsapp_stats()
        
        return {
            "total_messages": len(self.messages),
            "actionable_items": len(self.actionable_items),
            "todo_stats": todo_stats,
            "recent_senders": list(set(msg.sender for msg in self.messages[-20:]))
        }

# Global instance for use across the application
whatsapp_integration = WhatsAppIntegration()

# Tool function for Marin integration
def tool_whatsapp_manage(action: str, message_data: str = None, limit: int = 10) -> str:
    """
    WhatsApp integration tool for Marin.
    Actions: 'process', 'list_messages', 'list_todos', 'stats', 'list_actionable'
    """
    try:
        if action == "process" and message_data:
            # Process incoming WhatsApp message
            data = json.loads(message_data)
            sender = data.get("sender", "Unknown")
            content = data.get("content", "")
            chat_name = data.get("chat_name", "Unknown")
            is_group = data.get("is_group", False)
            
            # Run async processing
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            items = loop.run_until_complete(
                whatsapp_integration.process_whatsapp_message(sender, content, chat_name, is_group)
            )
            loop.close()
            
            if items:
                return f"Processed message from {sender}. Found {len(items)} actionable item(s). Created todos for high-confidence items."
            return f"Processed message from {sender}. No actionable items found."
        
        elif action == "list_messages":
            messages = whatsapp_integration.get_recent_messages(limit)
            if not messages:
                return "No WhatsApp messages recorded yet."
            
            result = f"Recent {len(messages)} WhatsApp messages:\n"
            for msg in messages[-10:]:  # Show last 10
                result += f"- [{msg.sender}] {msg.content[:50]}{'...' if len(msg.content) > 50 else ''}\n"
            return result
        
        elif action == "list_todos":
            todos = whatsapp_integration.todo_manager.get_whatsapp_todos(limit)
            if not todos:
                return "No todos created from WhatsApp messages yet."
            
            result = f"WhatsApp-generated todos ({len(todos)}):\n"
            for todo in todos:
                status_icon = "✅" if todo['status'] == 'done' else "⏳"
                result += f"{status_icon} {todo['id']}. {todo['title']} [{todo['priority']}] (from {todo['sender']})\n"
            return result
        
        elif action == "list_actionable":
            items = whatsapp_integration.get_actionable_items()
            if not items:
                return "No actionable items found in messages."
            
            result = f"Actionable items ({len(items)}):\n"
            for item in items[-10:]:  # Show last 10
                result += f"- [{item.action_type}] {item.extracted_text[:50]}{'...' if len(item.extracted_text) > 50 else ''} (conf: {item.confidence:.1f})\n"
            return result
        
        elif action == "stats":
            stats = whatsapp_integration.get_integration_stats()
            todo_stats = stats['todo_stats']
            total = todo_stats.get('total', 0) or 0
            pending = todo_stats.get('pending', 0) or 0
            completed = todo_stats.get('completed', 0) or 0
            avg_confidence = todo_stats.get('avg_confidence', 0) or 0
            return (
                f"WhatsApp Integration Stats:\n"
                f"Total messages: {stats['total_messages']}\n"
                f"Actionable items: {stats['actionable_items']}\n"
                f"Todos created: {total}\n"
                f"Pending todos: {pending}\n"
                f"Completed todos: {completed}\n"
                f"Avg confidence: {avg_confidence:.2f}"
            )
        
        else:
            return "Invalid action. Use: 'process', 'list_messages', 'list_todos', 'stats', or 'list_actionable'"
    
    except Exception as e:
        logger.error(f"WhatsApp tool error: {e}")
        return f"WhatsApp tool error: {str(e)}"

def whatsapp_notification_handler(message: WhatsAppMessage, items: List[ActionableItem]):
    """Handle WhatsApp notifications for Marin"""
    if items:
        logger.info(f"WhatsApp: {len(items)} actionable items from {message.sender}")
        # This could be extended to send Telegram notifications, update UI, etc.
    else:
        logger.debug(f"WhatsApp: Message from {message.sender} - no actionable items")

# Register the notification handler
whatsapp_integration.register_notification_callback(whatsapp_notification_handler)

if __name__ == "__main__":
    # Test the integration
    print("WhatsApp Integration Tool for Marin")
    print("This tool processes WhatsApp messages and creates todos.")
    print("\nExample usage:")
    print('  tool_whatsapp_manage("process", \'{"sender": "John", "content": "Please buy groceries tomorrow"}\')')
    print('  tool_whatsapp_manage("list_todos")')
    print('  tool_whatsapp_manage("stats")')
