with open("/home/sword/Documents/projects/marin/sentinel_engine.py", "r") as f:
    text = f.read()
import re
text = re.sub(r'(if "/" in model_name:\s*\n\s*model_name = DEFAULT_LOCAL_MODEL)',
              r'if "/" in model_name:\n        return None  # Do not fallback to ollama for remote models',
              text)
with open("/home/sword/Documents/projects/marin/sentinel_engine.py", "w") as f:
    f.write(text)
