import re

with open("/home/sword/Documents/projects/marin/utils/agent_logic.py", "r") as f:
    py = f.read()

# Fix how tool_result for youtube_search_tool is saved
py = py.replace(
    """            if tool_result and intent in ["youtube_search_tool"]:
                yield tool_result
                database.save_message("marin", "user", prompt, user_id=user_id, session_id=session_id)
                database.save_message("marin", "assistant", tool_result, user_id=user_id, session_id=session_id)
                return""",
    """            if tool_result and intent in ["youtube_search_tool"]:
                yield tool_result
                # Don't leak system event tool instructions into the LLM's chat history
                save_prompt = prompt
                if "[SYSTEM EVENT" in prompt:
                    save_prompt = "(User quietly pasted a link to the TV)"
                database.save_message("marin", "user", save_prompt, user_id=user_id, session_id=session_id)
                database.save_message("marin", "assistant", tool_result, user_id=user_id, session_id=session_id)
                return"""
)

with open("/home/sword/Documents/projects/marin/utils/agent_logic.py", "w") as f:
    f.write(py)
