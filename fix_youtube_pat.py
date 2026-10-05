import re

with open("/home/sword/Documents/projects/marin/marin_fier.py", "r") as f:
    py = f.read()

py = py.replace(
    r"_YOUTUBE_PAT = re.compile(r'\b(youtube|yt|video|videos|watch|song|music|play)\b')",
    r"_YOUTUBE_PAT = re.compile(r'\b(youtube|yt|video|videos|watch|song|music|play|documentary|movie|show|episode)\b')"
)

py = py.replace(
    r"query = re.sub(r'\b(search|find|play|watch|youtube|video|videos|song|music|for)\b', '', lower).strip()",
    r"query = re.sub(r'\b(search|find|play|watch|youtube|video|videos|song|music|for|documentary|movie|show|episode)\b', '', lower).strip()"
)

with open("/home/sword/Documents/projects/marin/marin_fier.py", "w") as f:
    f.write(py)
