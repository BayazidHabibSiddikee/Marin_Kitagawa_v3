import re

with open("/home/sword/Documents/projects/marin/main.py", "r") as f:
    py = f.read()

api_chat_code = """
@app.post("/api/chat")
async def api_chat_endpoint(
    request: Request,
    message: str = Form(...),
    theme: str = Form(None),
    document: str = Form(None),
    tool_context: str = Form(None)
):
    from proactive_engine import record_user_message
    record_user_message("marin")
    user = request.state.user

    enhanced_prompt = message
    if document:
        enhanced_prompt += f"\\n\\n[Context Document excerpt: {document[:2000]}]"
    if tool_context:
        enhanced_prompt += f"\\n\\n[Tool Context: {tool_context}]"

    return StreamingResponse(
        stream_marin_chat(enhanced_prompt, user=user, session_id="library"),
        media_type="text/plain"
    )

@app.post("/message")
"""

py = py.replace('@app.post("/message")', api_chat_code)

with open("/home/sword/Documents/projects/marin/main.py", "w") as f:
    f.write(py)
