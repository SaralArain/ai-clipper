import glob
import os
import subprocess
import time

import requests

from utils.helpers import merge_snippets

GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


def fetch_youtube_lines(video_id: str, languages=("en", "hi", "ur")):
    """Fast + free: use YouTube's own captions (manual or auto-generated)."""
    from youtube_transcript_api import YouTubeTranscriptApi

    api = YouTubeTranscriptApi()
    try:
        fetched = api.fetch(video_id, languages=list(languages))
    except Exception:
        # preferred languages missing -> take whatever transcript exists
        fetched = next(iter(api.list(video_id))).fetch()
    snippets = [(s.start, s.duration, s.text) for s in fetched]
    return merge_snippets(snippets)


def _split_audio(src: str, out_dir: str, chunk_sec: int):
    """Convert to small mono mp3 chunks so each stays under Groq's 25 MB limit."""
    pattern = os.path.join(out_dir, "chunk_%03d.mp3")
    cmd = ["ffmpeg", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-b:a", "32k",
           "-f", "segment", "-segment_time", str(chunk_sec), "-reset_timestamps", "1", pattern]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg audio extraction failed: " + r.stderr[-400:])
    return sorted(glob.glob(os.path.join(out_dir, "chunk_*.mp3")))


def transcribe_with_groq(media_path: str, api_key: str, work_dir: str, language=None,
                         model: str = "whisper-large-v3-turbo", chunk_sec: int = 1200,
                         progress_cb=None):
    """Speech-to-text through Groq's free Whisper API (works for any audio/video file)."""
    chunk_dir = os.path.join(work_dir, "chunks")
    os.makedirs(chunk_dir, exist_ok=True)
    for old in glob.glob(os.path.join(chunk_dir, "chunk_*.mp3")):
        os.remove(old)
    chunks = _split_audio(media_path, chunk_dir, chunk_sec)
    if not chunks:
        raise RuntimeError("No audio found in this file.")

    snippets = []
    for i, path in enumerate(chunks):
        if progress_cb:
            progress_cb(i, len(chunks))
        data = {"model": model, "response_format": "verbose_json",
                "timestamp_granularities[]": "segment"}
        if language:
            data["language"] = language
        r = None
        for attempt in range(4):
            with open(path, "rb") as f:
                r = requests.post(
                    GROQ_STT_URL,
                    headers={"Authorization": f"Bearer {api_key}"},
                    data=data,
                    files={"file": (os.path.basename(path), f, "audio/mpeg")},
                    timeout=300,
                )
            if r.status_code in (429, 500, 502, 503):
                time.sleep(min(30, 6 * (attempt + 1)))
                continue
            break
        if r is None or r.status_code != 200:
            raise RuntimeError(f"Groq transcription failed ({r.status_code}): {r.text[:300]}")
        for seg in r.json().get("segments", []):
            snippets.append((seg["start"] + i * chunk_sec, seg["end"] - seg["start"], seg["text"]))
    return merge_snippets(snippets)
