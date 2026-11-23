import os
import shutil
import tempfile

import streamlit as st

from core.analyzer import DEFAULT_MODELS, find_viral_clips
from core.captions import build_srt
from core.clipper import LAYOUTS, render_clip
from core.downloader import download_audio, download_section
from core.transcriber import fetch_youtube_lines, transcribe_with_groq
from utils.helpers import extract_video_id, fmt_time

st.set_page_config(page_title="AI Clipper", page_icon="🎬", layout="wide")
ss = st.session_state
for k, v in {"workdir": None, "lines": None, "clips": [], "source": None, "url": None,
             "local_path": None, "rendered": {}, "run_id": 0}.items():
    ss.setdefault(k, v)


def secret(name: str) -> str:
    try:
        return st.secrets.get(name, "") or os.environ.get(name, "")
    except Exception:
        return os.environ.get(name, "")


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    provider = st.selectbox("AI provider (free tier)", ["Groq", "Gemini"])
    groq_key = st.text_input("Groq API key", value=secret("GROQ_API_KEY"), type="password",
                             help="Free at console.groq.com. Also used for Whisper speech-to-text.")
    gemini_key = ""
    if provider == "Gemini":
        gemini_key = st.text_input("Gemini API key", value=secret("GEMINI_API_KEY"), type="password",
                                   help="Free at aistudio.google.com/apikey")
    model = st.text_input("Model", value=DEFAULT_MODELS[provider], key=f"model_{provider}")
    st.divider()
    n_clips = st.slider("Number of clips", 1, 10, 5)
    min_len, max_len = st.slider("Clip length (seconds)", 10, 120, (20, 60))
    layout = st.selectbox("Layout", LAYOUTS)
    captions_on = st.checkbox("Burn-in captions", value=True)
    st.divider()
    cookies_file = st.file_uploader("Optional cookies.txt", type=["txt"],
                                    help="Only needed if YouTube blocks downloads from the server.")


def ensure_workdir():
    if not ss.workdir or not os.path.isdir(ss.workdir):
        ss.workdir = tempfile.mkdtemp(prefix="clipper_")


def cookies_path():
    if not cookies_file:
        return None
    ensure_workdir()
    path = os.path.join(ss.workdir, "cookies.txt")
    with open(path, "wb") as f:
        f.write(cookies_file.getvalue())
    return path


def reset_workdir():
    if ss.workdir and os.path.isdir(ss.workdir):
        shutil.rmtree(ss.workdir, ignore_errors=True)
    ss.workdir = tempfile.mkdtemp(prefix="clipper_")
    ss.rendered, ss.clips, ss.lines = {}, [], None
    ss.run_id += 1


# --------------------------------------------------------------------- main
st.title("🎬 AI Clipper")
st.caption("Paste a YouTube stream/video or upload a file. AI finds the most viral moments and cuts them into clips.")

mode = st.radio("Video source", ["YouTube URL", "Upload video"], horizontal=True)
url, uploaded = "", None
if mode == "YouTube URL":
    url = st.text_input("YouTube URL (finished stream / video)", placeholder="https://www.youtube.com/watch?v=...")
else:
    uploaded = st.file_uploader("Video file", type=["mp4", "mov", "mkv", "webm", "mp3", "m4a", "wav"])

if st.button("🔍 Find viral moments", type="primary"):
    llm_key = groq_key if provider == "Groq" else gemini_key
    problem = None
    if not llm_key:
        problem = f"Please add your {provider} API key in the sidebar."
    elif mode == "YouTube URL" and not extract_video_id(url):
        problem = "That doesn't look like a valid YouTube link."
    elif mode == "Upload video" and uploaded is None:
        problem = "Please upload a video file."
    elif mode == "Upload video" and not groq_key:
        problem = "Uploaded files are transcribed with Groq Whisper - add a Groq API key."

    if problem:
        st.error(problem)
    else:
        reset_workdir()
        with st.status("Analyzing…", expanded=True) as status:
            try:
                lines = None
                if mode == "YouTube URL":
                    vid = extract_video_id(url)
                    ss.update(source="yt", url=url, local_path=None)
                    st.write("📄 Fetching YouTube captions…")
                    try:
                        lines = fetch_youtube_lines(vid)
                    except Exception as e:
                        st.write(f"No captions available ({type(e).__name__}) - using speech-to-text instead.")
                    if not lines:
                        if not groq_key:
                            raise RuntimeError("This video has no captions. Add a Groq API key to transcribe the audio.")
                        st.write("⬇️ Downloading audio…")
                        audio = download_audio(url, ss.workdir, cookies_path())
                        st.write("🎙️ Transcribing with Whisper…")
                        lines = transcribe_with_groq(audio, groq_key, ss.workdir)
                else:
                    local = os.path.join(ss.workdir, "source_" + os.path.basename(uploaded.name))
                    with open(local, "wb") as f:
                        f.write(uploaded.getbuffer())
                    ss.update(source="file", url=None, local_path=local)
                    st.write("🎙️ Transcribing with Whisper…")
                    lines = transcribe_with_groq(local, groq_key, ss.workdir)

                if not lines:
                    raise RuntimeError("Could not get a transcript for this video.")

                st.write(f"🧠 Finding viral moments with {provider} ({len(lines)} transcript lines)…")
                bar = st.progress(0.0)
                clips = find_viral_clips(
                    lines, provider, llm_key, model, n_clips, min_len, max_len,
                    progress_cb=lambda i, n: bar.progress(i / max(n, 1)),
                )
                bar.progress(1.0)
                ss.lines, ss.clips = lines, clips
                status.update(label=f"Done - found {len(clips)} clips", state="complete", expanded=False)
            except Exception as e:
                status.update(label="Failed", state="error")
                st.error(str(e))


def render_one(i: int):
    c = ss.clips[i]
    start = float(ss.get(f"s_{ss.run_id}_{i}", c["start"]))
    end = float(ss.get(f"e_{ss.run_id}_{i}", c["end"]))
    if end <= start:
        raise ValueError("End time must be after start time.")
    stem = f"clip_{ss.run_id}_{i + 1}"
    if ss.source == "yt":
        src = download_section(ss.url, start, end, ss.workdir, stem + "_raw", cookies_path())
        offset = 0.0
    else:
        src, offset = ss.local_path, start
    srt_path = None
    if captions_on:
        srt = build_srt(ss.lines, start, end)
        if srt:
            srt_path = os.path.join(ss.workdir, stem + ".srt")
            with open(srt_path, "w", encoding="utf-8") as f:
                f.write(srt)
    out = os.path.join(ss.workdir, stem + "_final.mp4")
    render_clip(src, out, offset, end - start, layout, srt_path, ss.workdir)
    ss.rendered[i] = out


def safe_render(i: int):
    try:
        with st.spinner(f"Creating clip {i + 1}…"):
            render_one(i)
    except Exception as e:
        st.error(f"Clip {i + 1} failed: {e}")
        if ss.source == "yt":
            st.info("If YouTube blocked the download, upload the video file instead, "
                    "or add a cookies.txt in the sidebar.")


if ss.clips:
    st.divider()
    head, btn = st.columns([3, 1])
    head.subheader(f"Top {len(ss.clips)} viral moments")
    if btn.button("⚡ Create all clips"):
        for i in range(len(ss.clips)):
            safe_render(i)

    for i, c in enumerate(ss.clips):
        with st.container(border=True):
            left, right = st.columns(2)
            with left:
                start_s, end_s = int(c["start"]), int(c["end"])
                if ss.source == "yt":
                    st.video(ss.url, start_time=start_s, end_time=end_s)
                else:
                    st.video(ss.local_path, start_time=start_s, end_time=end_s)
            with right:
                st.markdown(f"### {i + 1}. {c['title']}")
                st.markdown(f"🔥 **Viral score: {c['score']}/100** · ⏱️ {fmt_time(c['start'])} → "
                            f"{fmt_time(c['end'])} ({int(c['end'] - c['start'])}s)")
                st.write(c["reason"])
                with st.expander("Fine-tune start / end (seconds)"):
                    st.number_input("Start", value=float(c["start"]), step=1.0, key=f"s_{ss.run_id}_{i}")
                    st.number_input("End", value=float(c["end"]), step=1.0, key=f"e_{ss.run_id}_{i}")
                if st.button("🎞️ Create clip", key=f"mk_{ss.run_id}_{i}"):
                    safe_render(i)

            path = ss.rendered.get(i)
            if path and os.path.exists(path):
                st.video(path)
                with open(path, "rb") as f:
                    st.download_button("⬇️ Download MP4", f.read(), file_name=f"clip_{i + 1}.mp4",
                                       mime="video/mp4", key=f"dl_{ss.run_id}_{i}")
