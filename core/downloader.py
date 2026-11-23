import glob
import os

from yt_dlp import YoutubeDL
from yt_dlp.utils import download_range_func


def _find(out_dir: str, stem: str) -> str:
    files = [f for f in glob.glob(os.path.join(out_dir, stem + ".*"))
             if not f.endswith((".part", ".ytdl", ".srt"))]
    if not files:
        raise RuntimeError("Download finished but the file was not found.")
    mp4 = [f for f in files if f.endswith(".mp4")]
    return (mp4 or files)[0]


def _base_opts(cookies):
    opts = {"quiet": True, "no_warnings": True, "noprogress": True, "retries": 3}
    if cookies:
        opts["cookiefile"] = cookies
    return opts


def download_audio(url: str, out_dir: str, cookies=None) -> str:
    """Download a small audio-only file (used for speech-to-text fallback)."""
    opts = _base_opts(cookies)
    opts.update({
        "format": "bestaudio[abr<=64]/worstaudio/bestaudio",
        "outtmpl": os.path.join(out_dir, "audio.%(ext)s"),
    })
    with YoutubeDL(opts) as ydl:
        ydl.download([url])
    return _find(out_dir, "audio")


def download_section(url: str, start: float, end: float, out_dir: str, stem: str, cookies=None) -> str:
    """Download ONLY [start, end] seconds of the video (max 720p).

    This is what makes multi-hour streams possible: we never download the whole file.
    """
    opts = _base_opts(cookies)
    opts.update({
        "format": "bv*[height<=720]+ba/b[height<=720]/b",
        "outtmpl": os.path.join(out_dir, stem + ".%(ext)s"),
        "download_ranges": download_range_func(None, [(max(0.0, start), end)]),
        "force_keyframes_at_cuts": True,
        "merge_output_format": "mp4",
    })
    with YoutubeDL(opts) as ydl:
        ydl.download([url])
    return _find(out_dir, stem)
