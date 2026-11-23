def _ts(t: float) -> str:
    ms = int(round(max(t, 0) * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(lines, start: float, end: float, words_per_chunk: int = 4) -> str:
    """Build short, punchy SRT captions (a few words at a time) for [start, end].

    Timings inside each transcript line are estimated by spreading words evenly.
    Returned times are relative to the clip start. Empty string if no text.
    """
    entries = []
    for ln in lines:
        if ln.end <= start or ln.start >= end:
            continue
        words = ln.text.split()
        if not words:
            continue
        per = max(ln.end - ln.start, 0.1) / len(words)
        for i in range(0, len(words), words_per_chunk):
            chunk = words[i:i + words_per_chunk]
            cs = max(ln.start + i * per, start)
            ce = min(ln.start + (i + len(chunk)) * per, end)
            if ce - cs < 0.15:
                continue
            entries.append([cs - start, ce - start, " ".join(chunk).upper()])

    for k in range(len(entries) - 1):  # no overlaps
        if entries[k][1] > entries[k + 1][0]:
            entries[k][1] = entries[k + 1][0]
    entries = [e for e in entries if e[1] - e[0] > 0.05]

    out = []
    for n, (s, e, text) in enumerate(entries, 1):
        out.append(f"{n}\n{_ts(s)} --> {_ts(e)}\n{text}\n")
    return "\n".join(out)
