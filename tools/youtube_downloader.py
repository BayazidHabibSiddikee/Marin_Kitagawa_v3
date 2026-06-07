#!/usr/bin/env python3
"""
YouTube Downloader — yt-dlp wrapper for downloading videos and audio.
Part of the SwordFish Tools suite.
"""

import os
import yt_dlp
from typing import Dict, Any, Optional

DOWNLOAD_DIR = "static/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def get_video_info(url: str) -> Dict[str, Any]:
    """Get metadata for a YouTube video."""
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            return {
                "ok": True,
                "title": info.get('title'),
                "duration": info.get('duration'),
                "view_count": info.get('view_count'),
                "thumbnail": info.get('thumbnail'),
                "formats": [
                    {"format_id": f.get('format_id'), "ext": f.get('ext'), "resolution": f.get('resolution')}
                    for f in info.get('formats', []) if f.get('vcodec') != 'none'
                ]
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

def download_video(url: str, quality: str = "bestvideo+bestaudio/best", output_dir: str = DOWNLOAD_DIR) -> Dict[str, Any]:
    """Download a YouTube video."""
    ydl_opts = {
        'format': quality,
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            return {
                "ok": True,
                "title": info.get('title'),
                "filename": os.path.basename(filename),
                "path": filename
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

def download_audio(url: str, output_dir: str = DOWNLOAD_DIR) -> Dict[str, Any]:
    """Download audio only from a YouTube video."""
    ydl_opts = {
        'format': 'bestaudio/best',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': False,
        'no_warnings': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            # The prepare_filename gives the original ext, but postprocessor changes it to .mp3
            base_filename = ydl.prepare_filename(info)
            filename = os.path.splitext(base_filename)[0] + ".mp3"
            return {
                "ok": True,
                "title": info.get('title'),
                "filename": os.path.basename(filename),
                "path": filename
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        url = sys.argv[1]
        action = sys.argv[2] if len(sys.argv) > 2 else "info"
        
        if action == "video":
            print(download_video(url))
        elif action == "audio":
            print(download_audio(url))
        else:
            print(get_video_info(url))
    else:
        print("Usage: python3 youtube_downloader.py <url> [video|audio|info]")
