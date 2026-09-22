"""Local, shell-free montage and technical media checks with FFmpeg."""
from __future__ import annotations

import json
import math
import mimetypes
import os
import shutil
import subprocess
import tempfile
from pathlib import Path


def _tool(name: str) -> str:
    tool = shutil.which(name)
    if not tool:
        raise ValueError(f"{name} is required; install FFmpeg and run kie-media doctor")
    return tool


def _run(argv: list[str], *, cwd=None) -> None:
    result = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=1800)
    if result.returncode:
        raise ValueError(f"Media processing failed: {result.stderr[-3000:]}")


def probe(path: Path) -> dict:
    path = path.expanduser().resolve()
    if not path.is_file() or not path.stat().st_size:
        raise ValueError(f"Missing or empty media: {path}")
    result = subprocess.run([_tool("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError(f"Unreadable media: {path}")
    payload = json.loads(result.stdout)
    streams = payload.get("streams", [])
    video = next((s for s in streams if s.get("codec_type") == "video"), {})
    image_formats = {"image2", "image2pipe", "png_pipe", "jpeg_pipe", "webp_pipe", "bmp_pipe", "tiff_pipe", "gif"}
    is_image = bool(video) and payload.get("format", {}).get("format_name") in image_formats
    duration = float(payload.get("format", {}).get("duration") or video.get("duration") or 0)
    return {"file": str(path), "duration": duration, "width": video.get("width"), "height": video.get("height"),
            "image": is_image, "video": bool(video) and not is_image, "audio": any(s.get("codec_type") == "audio" for s in streams),
            "bytes": path.stat().st_size, "technical_check": "passed", "visual_review": "not_performed"}


def _timestamp(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, rest = divmod(milliseconds, 3600000)
    minutes, rest = divmod(rest, 60000)
    secs, millis = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def assemble_timeline(shots: list[dict], output: Path, *, aspect_ratio="16:9", music=None, captions=False) -> dict:
    sizes = {"16:9": (1280, 720), "9:16": (720, 1280), "1:1": (1080, 1080), "4:5": (864, 1080)}
    if aspect_ratio not in sizes or not shots:
        raise ValueError("A supported aspect ratio and at least one shot are required")
    width, height = sizes[aspect_ratio]
    output = output.expanduser().resolve()
    if output.exists():
        raise ValueError("Render target already exists; use a new file")
    output.parent.mkdir(parents=True, exist_ok=True)
    ffmpeg = _tool("ffmpeg")
    cursor, subtitle_lines, warnings = 0.0, [], []
    with tempfile.TemporaryDirectory(prefix=".kie-render-", dir=output.parent) as td:
        workspace = Path(td)
        for index, shot in enumerate(shots):
            clip = Path(shot["video"]).resolve()
            info = probe(clip)
            if not info["video"]:
                raise ValueError("Timeline shot is not a video")
            duration = float(shot["duration"])
            if not math.isfinite(duration) or not 0 < duration <= 600:
                raise ValueError("Invalid timeline duration")
            args = [ffmpeg, "-v", "error", "-i", str(clip)]
            if shot.get("voice"):
                voice = Path(shot["voice"]).resolve()
                audio_info = probe(voice)
                if not audio_info["audio"]:
                    raise ValueError("Narration has no audio stream")
                duration = max(duration, audio_info["duration"] + 0.15)
                args += ["-i", str(voice)]
                audio_input = "1:a:0"
            elif info["audio"]:
                audio_input = "0:a:0"
            else:
                args += ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo"]
                audio_input = "1:a:0"
            if duration > info["duration"] + 0.2:
                reason = "preserve narration" if shot.get("voice") and duration > float(shot["duration"]) else "meet shot duration"
                warnings.append(f"Shot {index + 1}: held last frame for {duration - info['duration']:.2f}s to {reason}")
            filters = (f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                       f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=30,"
                       f"tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},setpts=PTS-STARTPTS")
            args += ["-map", "0:v:0", "-map", audio_input, "-vf", filters,
                     "-af", f"apad,atrim=duration={duration},asetpts=PTS-STARTPTS",
                     "-t", str(duration), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                     "-c:a", "aac", "-ar", "48000", "-ac", "2", str(workspace / f"scene-{index}.mp4")]
            _run(args)
            if shot.get("narration"):
                subtitle_lines += [str(len(subtitle_lines) // 4 + 1), f"{_timestamp(cursor)} --> {_timestamp(cursor + duration)}",
                                   str(shot["narration"]).replace("\r", " ").replace("\n", " "), ""]
            cursor += duration
        (workspace / "segments.txt").write_text("\n".join(f"file 'scene-{i}.mp4'" for i in range(len(shots))), encoding="utf-8")
        _run([ffmpeg, "-v", "error", "-f", "concat", "-safe", "1", "-i", "segments.txt", "-c", "copy", "joined.mp4"], cwd=workspace)
        subtitle_path = workspace / "captions.srt"
        subtitle_path.write_text("\n".join(subtitle_lines), encoding="utf-8")
        args = [ffmpeg, "-v", "error", "-i", "joined.mp4"]
        if music:
            music_path = Path(music).resolve()
            if not probe(music_path)["audio"]:
                raise ValueError("Soundtrack has no audio stream")
            args += ["-stream_loop", "-1", "-i", str(music_path), "-filter_complex",
                     "[1:a]volume=0.12[m];[0:a][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[a]",
                     "-map", "0:v:0", "-map", "[a]"]
        else:
            args += ["-map", "0:v:0", "-map", "0:a:0"]
        if captions and subtitle_lines:
            args += ["-vf", "subtitles=captions.srt", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20"]
        else:
            args += ["-c:v", "copy"]
        args += ["-c:a", "aac", "-movflags", "+faststart", "-t", str(cursor), "final.mp4"]
        _run(args, cwd=workspace)
        final_info = probe(workspace / "final.mp4")
        if abs(final_info["duration"] - cursor) > 0.25 or not final_info["audio"]:
            raise ValueError("Rendered timeline failed duration/audio verification")
        os.replace(workspace / "final.mp4", output)
        subtitles = output.with_suffix(".srt")
        if subtitle_lines:
            os.replace(subtitle_path, subtitles)
    return {"file": str(output), "subtitles": str(subtitles) if subtitle_lines else None,
            "duration": cursor, "width": width, "height": height, "warnings": warnings,
            "caption_timing": "scene-aligned, not word-aligned", "visual_review": "not_performed"}
