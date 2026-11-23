import html
import re

from core.models import Line

_ID_RE = re.compile(r"(?:v=|/live/|/shorts/|/embed/|youtu\.be/)([A-Za-z0-9_-]{11})")


def extract_video_id(url: str):
    """Return the 11-char YouTube video id from a URL (or None)."""
    url = (url or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    m = _ID_RE.search(url)
    return m.group(1) if m else None


def fmt_time(sec: float) -> str:
    sec = int(max(0, sec))
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def clean_text(text: str) -> str:
    text = html.unescape(text or "")
    text = text.replace("\n", " ")
    text = re.sub(r"\[[^\]]*\]", " ", text)  # [Music], [Applause] ...
    text = re.sub(r"\s+", " ", text).strip()
    return text


def merge_snippets(snippets, min_len: float = 6.0, max_len: float = 14.0):
    """Merge tiny caption snippets (start, duration, text) into readable lines."""
    lines, cur = [], None
    for start, dur, text in snippets:
        text = clean_text(text)
        if not text:
            continue
        end = start + max(float(dur), 0.01)
        if cur is None:
            cur = Line(float(start), end, text)
        else:
            cur.text += " " + text
            cur.end = max(cur.end, end)
        length = cur.end - cur.start
        if length >= max_len or (length >= min_len and cur.text.endswith((".", "?", "!"))):
            lines.append(cur)
            cur = None
    if cur is not None:
        lines.append(cur)
    return lines
