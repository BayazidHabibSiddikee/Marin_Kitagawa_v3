with open("/home/sword/Documents/projects/marin/marin_fier.py", "r") as f:
    text = f.read()

old_res_check = """    # YouTube URLs specifically
    if re.search(r'(https?://(www\.)?(youtube\.com|youtu\.be)\S+)', lower):
        return {"intent": "youtube_search_tool", "params": {"query": lower}, "confidence": 1.0}"""

new_res_check = """    # YouTube URLs specifically
    yt_match = re.search(r'(https?://(www\.)?(youtube\.com|youtu\.be)[^\s\]\)]+)', lower)
    if yt_match:
        return {"intent": "youtube_search_tool", "params": {"query": yt_match.group(1)}, "confidence": 1.0}"""

text = text.replace(old_res_check, new_res_check)

with open("/home/sword/Documents/projects/marin/marin_fier.py", "w") as f:
    f.write(text)
