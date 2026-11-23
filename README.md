# 🎬 AI Clipper

Paste a YouTube video/stream recording (or upload a file) → AI finds the most viral moments → get ready-to-post vertical clips with captions. 100% free stack.

## How it works
1. Transcript: YouTube captions (free, instant) or Groq Whisper (free) if there are none / for uploads
2. AI (Groq Llama or Gemini, free tiers) scores transcript windows for hooks, emotion and complete stories
3. Clips are snapped to sentence boundaries, de-duplicated and ranked
4. Only the chosen time ranges are downloaded (yt-dlp), so multi-hour streams are fine
5. FFmpeg crops to 9:16, burns captions, and exports MP4

## Project structure
```
app.py                  Streamlit UI
core/analyzer.py        LLM viral-moment scoring
core/transcriber.py     YouTube captions + Groq Whisper
core/downloader.py      yt-dlp (audio + section download)
core/clipper.py         FFmpeg reframe + captions
core/captions.py        SRT builder
prompts/viral_prompt.txt  scoring prompt (edit to tune results)
utils/helpers.py        helpers
requirements.txt        Python packages
packages.txt            system packages (ffmpeg, font)
.streamlit/             config + secrets example
```

## Free API keys
- Groq: https://console.groq.com/keys
- Gemini (optional): https://aistudio.google.com/apikey

## Run locally
```
pip install -r requirements.txt
# install ffmpeg (e.g. `sudo apt install ffmpeg` / `brew install ffmpeg`)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml   # add your keys
streamlit run app.py
```

## Deploy free on Streamlit Community Cloud
1. Push this folder to a GitHub repo (`secrets.toml` is git-ignored).
2. Go to https://share.streamlit.io → New app → pick the repo, main file `app.py`.
3. App → Settings → Secrets → paste `GROQ_API_KEY = "..."` (and `GEMINI_API_KEY` if used).
4. Deploy. `packages.txt` installs ffmpeg automatically.

## Known limits and fixes
- **YouTube may block downloads from cloud servers.** Captions + AI analysis still work; if clip download fails, upload the video file instead, or add a `cookies.txt` in the sidebar, or run the app locally.
- Keep `yt-dlp` updated (redeploy/reboot the app) - YouTube changes often.
- Only works on finished videos/stream recordings, not streams that are live right now.
- Free tiers have rate limits; very long streams take a few minutes to analyze.
- Only clip content you own or have permission to use.
