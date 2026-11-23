import os
import subprocess

LAYOUTS = [
    "Vertical 9:16 - center crop",
    "Vertical 9:16 - blurred background",
    "Original (no resize)",
]

CAPTION_STYLE = ("FontName=DejaVu Sans,Bold=1,FontSize=10,PrimaryColour=&H00FFFFFF,"
                 "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
                 "Alignment=2,MarginV=70")


def _filter_graph(layout: str, srt_name):
    if layout == LAYOUTS[0]:
        base = "[0:v]crop='min(iw,ih*9/16)':ih,scale=1080:1920,setsar=1[v0]"
    elif layout == LAYOUTS[1]:
        base = ("[0:v]split[a][b];"
                "[a]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg];"
                "[b]scale=1080:1920:force_original_aspect_ratio=decrease[fg];"
                "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]")
    else:
        base = "[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2[v0]"

    if srt_name:
        return f"{base};[v0]subtitles={srt_name}:force_style='{CAPTION_STYLE}'[vout]"
    return f"{base};[v0]null[vout]"


def render_clip(src: str, out_path: str, ss: float, duration: float, layout: str,
                srt_path, work_dir: str):
    """Cut [ss, ss+duration] from src, reframe it, burn captions, write an MP4."""
    srt_name = None
    if srt_path:
        srt_name = os.path.basename(srt_path)  # ffmpeg runs inside work_dir -> no path escaping
    cmd = [
        "ffmpeg", "-y", "-ss", f"{ss:.3f}", "-i", os.path.abspath(src), "-t", f"{duration:.3f}",
        "-filter_complex", _filter_graph(layout, srt_name),
        "-map", "[vout]", "-map", "0:a?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart",
        os.path.abspath(out_path),
    ]
    r = subprocess.run(cmd, cwd=work_dir, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg failed: " + r.stderr[-600:])
    return out_path
