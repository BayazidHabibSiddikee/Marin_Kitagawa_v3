# WhatsApp Integration with Marin

## Overview
This integration allows Marin to monitor WhatsApp messages and automatically create todos from actionable items. The system uses the existing WhatsApp automation tool (Camoufox-based) and integrates it with Marin's todo system.

## Features
- **Automatic Message Processing**: WhatsApp messages are parsed for actionable items
- **Smart Todo Creation**: Messages containing tasks, deadlines, or requests are converted to todos
- **Priority Detection**: High-priority keywords (urgent, ASAP, etc.) are detected
- **Source Tracking**: Todos track which WhatsApp message they came from
- **Statistics**: Get insights on WhatsApp-generated tasks

## How It Works

### 1. Message Monitoring
The WhatsApp automation tool (`tools/whatsapp_auto.py`) monitors WhatsApp Web using a stealth browser (Camoufox) and captures new messages.

### 2. Message Parsing
When a new message arrives, it's processed by the `WhatsAppMessageParser` which:
- Detects todo patterns ("please buy", "need to", "remember to")
- Identifies deadlines ("by tomorrow", "due Friday")
- Recognizes questions ("what time", "can you")
- Determines priority based on keywords

### 3. Todo Creation
High-confidence actionable items (confidence ≥ 0.7) are automatically created as todos in the existing `storage/todos.db` database.

### 4. Integration with Marin
The integration is registered as a tool in Marin's tool system, allowing Marin to:
- Process WhatsApp messages manually or automatically
- List todos created from WhatsApp
- Get statistics on WhatsApp integration
- View recent messages

## Usage

### Via Marin Chat
You can interact with the WhatsApp integration through Marin's chat interface:

```
"Show me my WhatsApp todos"
"Process this WhatsApp message: [message data]"
"Get WhatsApp integration stats"
"List recent WhatsApp messages"
```

### Via API
The integration provides several actions:

```python
from tools.whatsapp_integration import tool_whatsapp_manage

# Process a WhatsApp message
message_data = '{"sender": "John", "content": "Please buy groceries tomorrow"}'
result = tool_whatsapp_manage("process", message_data)

# List todos created from WhatsApp
todos = tool_whatsapp_manage("list_todos")

# Get integration stats
stats = tool_whatsapp_manage("stats")

# List recent messages
messages = tool_whatsapp_manage("list_messages")
```

### Via WhatsApp Automation
The WhatsApp automation tool (`tools/whatsapp_auto.py`) automatically processes incoming messages and creates todos when high-confidence actionable items are detected.

## Database Structure

### Todos Table (existing)
- `id`: Todo ID
- `title`: Task description
- `priority`: high/medium/low
- `status`: todo/in-progress/done
- `created_at`: Creation timestamp
- `completed_at`: Completion timestamp

### WhatsApp Todos Table (new)
- `id`: WhatsApp todo ID
- `todo_id`: Reference to todos table
- `sender`: WhatsApp sender name
- `chat_name`: WhatsApp chat/group name
- `original_message`: Original message content
- `extracted_text`: Extracted actionable text
- `confidence`: Confidence score (0-1)
- `created_at`: Creation timestamp

## Example Messages

### Messages that create todos:
- "Please buy groceries tomorrow"
- "Need to submit report by Friday"
- "Remember to call mom"
- "URGENT: Review document ASAP"
- "Can you pick up milk?"

### Messages that don't create todos:
- "Hello, how are you?"
- "Meeting at 3pm" (unless it contains task indicators)
- "Thanks for your help"

## Configuration

### Confidence Threshold
By default, only messages with confidence ≥ 0.7 create todos. This can be adjusted in `tools/whatsapp_integration.py`:

```python
# In process_whatsapp_message method
if item.confidence >= 0.7:  # Only create todos for high-confidence items
    todo_id = self.todo_manager.create_todo_from_actionable_item(item)
```

### Priority Detection
Priority is determined by keywords:
- **High**: urgent, asap, emergency, important, critical, now
- **Medium**: soon, today, this week, priority
- **Low**: whenever, sometime, later, no rush

## Integration Points

### 1. WhatsApp Automation Tool
The existing `tools/whatsapp_auto.py` has been updated to:
- Import the WhatsApp integration tool
- Process incoming messages through Marin's integration
- Create todos automatically from high-confidence items

### 2. Marin's Tool System
The WhatsApp tool is registered in `marin_fier.py` as `whatsapp_manage`, allowing Marin to:
- Access WhatsApp data through natural language
- Process messages on demand
- Get statistics and insights

### 3. LangGraph Agent
The tool is available to Marin's LangGraph agent, enabling:
- Multi-step workflows involving WhatsApp
- Automatic response generation
- Integration with other Marin tools

## Monitoring and Notifications

### Notification System
The integration includes a notification system that can be extended to:
- Send Telegram notifications for important messages
- Update the web dashboard
- Trigger other automated actions

### Statistics
Get insights with:
```python
stats = tool_whatsapp_manage("stats")
# Returns: total messages, actionable items, todos created, pending/completed, avg confidence
```

## Troubleshooting

### Common Issues

1. **No todos created**
   - Check if messages contain actionable patterns
   - Verify confidence threshold (default 0.7)
   - Check logs for parsing errors

2. **Database errors**
   - Ensure `storage/todos.db` exists and is writable
   - Check that the `whatsapp_todos` table was created

3. **Import errors**
   - Verify Python path includes the marin directory
   - Check that all dependencies are installed

### Logs
Check logs in `logs/tool_execution.log` for:
- Message processing results
- Todo creation events
- Error messages

## Future Enhancements

1. **Machine Learning**: Train a model to better identify actionable items
2. **Context Awareness**: Consider conversation context for better parsing
3. **Multi-language Support**: Extend pattern matching to other languages
4. **Integration with Calendar**: Convert deadlines to calendar events
5. **Smart Responses**: Auto-respond to simple WhatsApp queries
6. **Voice Messages**: Process voice message transcriptions
7. **Media Handling**: Extract tasks from images and documents

## Security Notes

- The WhatsApp automation uses a stealth browser (Camoufox) to avoid detection
- Login credentials are stored in `~/.camoufox_whatsapp_profile`
- No message content is sent to external services
- All processing happens locally on your machine

## Testing

Run the test script to verify the integration:
```bash
python3 test_whatsapp_integration.py
```

This will process sample messages and demonstrate the todo creation functionality.
