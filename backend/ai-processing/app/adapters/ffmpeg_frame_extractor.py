import asyncio
from pathlib import Path

from app.media_processing import extract_video_frames


class FfmpegFrameExtractor:
    """Run the existing FFmpeg frame extraction behind the application port."""

    async def extract(
        self,
        video_path: Path,
        output_directory: Path,
        frame_count: int,
    ) -> list[Path]:
        return await asyncio.to_thread(
            extract_video_frames,
            video_path,
            output_directory,
            frame_count,
        )
