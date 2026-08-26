from pathlib import Path
from typing import Protocol


class FrameExtractor(Protocol):
    """Extract representative image frames from one video."""

    async def extract(
        self,
        video_path: Path,
        output_directory: Path,
        frame_count: int,
    ) -> list[Path]: ...
