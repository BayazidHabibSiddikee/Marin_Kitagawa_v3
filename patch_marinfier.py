with open("/home/sword/Documents/projects/marin/marin_fier.py", "r") as f:
    text = f.read()

# Find _RESOURCE_PAT check
old_res_check = """    # Resource / URL downloader — before code/terminal checks
    if _RESOURCE_PAT.search(lower):
        return {"intent": "resource_tool", "params": {"query": lower}, "confidence": 0.95}"""

new_res_check = """    # YouTube URLs specifically
    if re.search(r'(https?://(www\.)?(youtube\.com|youtu\.be)\S+)', lower):
        return {"intent": "youtube_search_tool", "params": {"query": lower}, "confidence": 1.0}

    # Resource / URL downloader — before code/terminal checks
    if _RESOURCE_PAT.search(lower):
        return {"intent": "resource_tool", "params": {"query": lower}, "confidence": 0.95}"""

text = text.replace(old_res_check, new_res_check)

with open("/home/sword/Documents/projects/marin/marin_fier.py", "w") as f:
    f.write(text)
