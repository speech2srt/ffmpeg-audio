"""
FFmpeg Audio - A Python library for streaming audio/video files using FFmpeg.

This package provides utilities for:
- Streaming audio/video files in chunks
- Reading specific time segments from audio files
- Automatic resampling and channel mixing
"""

import logging

from .exceptions import FFmpegAudioError, FFmpegNotFoundError, UnsupportedFormatError
from .ffmpeg_audio import FFmpegAudio

__version__ = "0.1.0"

# Configure library root logger
# Use NullHandler to ensure library remains silent when user hasn't configured logging
# If user configures logging (e.g., logging.basicConfig()), logs will bubble up to root logger for processing
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

__all__ = [
    "FFmpegAudio",
    "FFmpegNotFoundError",
    "FFmpegAudioError",
    "UnsupportedFormatError",
]

