import re

def extract_youtube_url(text: str):
    """Pull YouTube URL from user message if present."""
    pattern = r'(https?://(?:www\.)?(?:youtube\.com/watch\?v=|youtu\.be/)[\w\-]+)'
    match = re.search(pattern, text)
    return match.group(1) if match else None

def get_youtube_transcript(url: str, return_raw: bool = False) -> str | list:
    try:
        from youtube_transcript_api import YouTubeTranscriptApi

        vid_id = None
        if "youtu.be/" in url:
            vid_id = url.split("youtu.be/")[1].split("?")[0]
        elif "v=" in url:
            vid_id = url.split("v=")[1].split("&")[0]

        if not vid_id:
            return None

        ytt_api = YouTubeTranscriptApi()
        transcript_list = ytt_api.list(vid_id)

        transcript = None
        for t in transcript_list:
            transcript = t
            break

        if not transcript:
            return None

        if transcript.language_code != "en" and transcript.is_translatable:
            transcript = transcript.translate("en")

        fetched = transcript.fetch()
        
        if return_raw:
            return fetched

        full_text = " ".join([entry["text"] for entry in fetched])
        if len(full_text) > 3000:
            full_text = full_text[:3000]
        return full_text
    except Exception as e:
        print(f"[Marin] Transcript fetch failed: {e}")
        return None
