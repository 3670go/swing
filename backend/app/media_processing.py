import json
import subprocess
from pathlib import Path


class MediaProcessingError(RuntimeError):
    """FFmpeg could not produce a bounded visual input set."""


def probe_duration_seconds(video_path: Path) -> float:
    """Read media duration with ffprobe without decoding the full video."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        raise MediaProcessingError("ffprobe could not read the selected video")
    try:
        duration = float(json.loads(result.stdout)["format"]["duration"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise MediaProcessingError("Video duration is unavailable") from error
    if duration <= 0:
        raise MediaProcessingError("Video duration must be positive")
    return duration


def extract_video_frames(video_path: Path, output_dir: Path, frame_count: int) -> list[Path]:
    """Extract evenly spaced frames while avoiding only the first and last instant."""
    duration = probe_duration_seconds(video_path)
    timestamps = [duration * (index + 1) / (frame_count + 1) for index in range(frame_count)]
    frames: list[Path] = []

    for index, timestamp in enumerate(timestamps, start=1):
        frame_path = output_dir / f"frame_{index:02d}.jpg"
        result = subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-ss",
                f"{timestamp:.3f}",
                "-i",
                str(video_path),
                "-frames:v",
                "1",
                "-vf",
                "scale='min(1280,iw)':-2",
                "-q:v",
                "3",
                "-y",
                str(frame_path),
            ],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0 or not frame_path.exists():
            raise MediaProcessingError(f"Could not extract frame {index}")
        frames.append(frame_path)

    return frames
