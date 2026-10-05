with open("/home/sword/Documents/projects/marin/langgraph_agent.py", "r") as f:
    text = f.read()

old_yt_desc = '    """Search YouTube for a video or music, classify its mood from the transcript,\n    and return a timed director animation sequence for Marin to perform.'
new_yt_desc = '    """Search YouTube for a video/music OR play a direct YouTube URL, classify its mood from the transcript,\n    and return a timed director animation sequence for Marin to perform.\n    CRITICAL: ALWAYS use this tool for ALL YouTube links/URLs!'
text = text.replace(old_yt_desc, new_yt_desc)

old_res_desc = '    """Download or analyze any resource. PDFs are downloaded and indexed. Webpages are fetched and summarized. GitHub repos are cloned. Use for any URL the user provides."""'
new_res_desc = '    """Download or analyze any resource. PDFs are downloaded and indexed. Webpages are fetched and summarized. GitHub repos are cloned. Use for general URLs. DO NOT use this for YouTube URLs (use youtube_search_tool instead)."""'
text = text.replace(old_res_desc, new_res_desc)

with open("/home/sword/Documents/projects/marin/langgraph_agent.py", "w") as f:
    f.write(text)
