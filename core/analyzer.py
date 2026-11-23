import json
import os
import re
import time

import requests

from utils.helpers import fmt_time

PROMPT_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "prompts", "viral_prompt.txt")
GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

DEFAULT_MODELS = {"Groq": "llama-3.3-70b-versatile", "Gemini": "gemini-2.5-flash"}


# ---------------------------------------------------------------- LLM calls
def _post(url, headers, payload, tries=4):
    last = None
    for attempt in range(tries):
        r = requests.post(url, headers=headers, json=payload, timeout=120)
        if r.status_code == 200:
            return r.json()
        last = r
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(40, 6 * (attempt + 1)))
            continue
        break
    raise RuntimeError(f"LLM API error {last.status_code}: {last.text[:300]}")


def call_llm(provider: str, api_key: str, model: str, system: str, user: str) -> str:
    if provider == "Groq":
        data = _post(
            GROQ_CHAT_URL,
            {"Authorization": f"Bearer {api_key}"},
            {"model": model, "temperature": 0.3,
             "response_format": {"type": "json_object"},
             "messages": [{"role": "system", "content": system},
                          {"role": "user", "content": user}]},
        )
        return data["choices"][0]["message"]["content"]

    data = _post(
        GEMINI_URL.format(model=model),
        {"x-goog-api-key": api_key},
        {"systemInstruction": {"parts": [{"text": system}]},
         "contents": [{"role": "user", "parts": [{"text": user}]}],
         "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}},
    )
    return data["candidates"][0]["content"]["parts"][0]["text"]


def parse_clips(raw: str):
    raw = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.MULTILINE).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        a, b = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[a:b + 1])
    if isinstance(data, list):
        return data
    return data.get("clips", [])


# ------------------------------------------------------------ transcript prep
def make_windows(lines, window_sec=600, overlap_sec=60):
    """Split a long transcript into overlapping windows so each LLM call stays small."""
    if not lines:
        return []
    t_end = lines[-1].end
    windows, s = [], lines[0].start
    while s < t_end:
        e = s + window_sec
        w = [l for l in lines if l.end > s and l.start < e]
        if w:
            windows.append(w)
        if e >= t_end:
            break
        s = e - overlap_sec
    return windows


def snap(lines, start, end, min_len, max_len):
    """Snap a suggested range to real sentence boundaries and enforce length limits."""
    s = min(lines, key=lambda l: abs(l.start - start)).start
    ends = [l.end for l in lines if l.end > s]
    if not ends:
        return s, s + min_len
    e = min(ends, key=lambda x: abs(x - end))
    if e - s > max_len:
        ok = [x for x in ends if x - s <= max_len]
        e = max(ok) if ok else s + max_len
    if e - s < min_len:
        ok = [x for x in ends if x - s >= min_len]
        e = min(ok) if ok else s + min_len
    return s, e


def _overlap(a, b):
    return max(0.0, min(a["end"], b["end"]) - max(a["start"], b["start"]))


# ----------------------------------------------------------------- main entry
def find_viral_clips(lines, provider, api_key, model, n_clips=5, min_len=20, max_len=60,
                     progress_cb=None):
    """Return the top `n_clips` viral moments: [{start,end,score,title,reason}, ...]."""
    with open(PROMPT_PATH, encoding="utf-8") as f:
        system = f.read().replace("{{MIN}}", str(int(min_len))).replace("{{MAX}}", str(int(max_len)))

    windows = make_windows(lines)
    candidates, last_error = [], None
    for i, w in enumerate(windows):
        if progress_cb:
            progress_cb(i, len(windows))
        user = (f"Transcript segment {fmt_time(w[0].start)} to {fmt_time(w[-1].end)}. "
                f"Return up to 3 clips.\n\n"
                + "\n".join(f"[{int(l.start)}] {l.text}" for l in w))
        try:
            items = parse_clips(call_llm(provider, api_key, model, system, user))
        except Exception as e:  # keep going if one window fails
            last_error = e
            continue
        for it in items:
            try:
                s, e = snap(lines, float(it["start"]), float(it["end"]), min_len, max_len)
                candidates.append({
                    "start": s, "end": e,
                    "score": max(0, min(100, int(float(it.get("score", 0))))),
                    "title": str(it.get("title", "Untitled clip"))[:80],
                    "reason": str(it.get("reason", ""))[:300],
                })
            except (KeyError, ValueError, TypeError):
                continue
        time.sleep(0.5)

    if not candidates and last_error:
        raise last_error

    candidates.sort(key=lambda c: -c["score"])
    kept = []
    for c in candidates:
        length = max(c["end"] - c["start"], 1)
        if all(_overlap(c, k) / length < 0.2 for k in kept):
            kept.append(c)
        if len(kept) >= n_clips:
            break
    return kept
