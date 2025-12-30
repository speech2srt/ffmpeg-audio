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

# 配置库的根 logger
# 使用 NullHandler 确保库在用户未配置日志时保持静默
# 如果用户配置了日志（如 logging.basicConfig()），日志会向上冒泡到根 logger 被处理
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

__all__ = [
    "FFmpegAudio",
    "FFmpegNotFoundError",
    "FFmpegAudioError",
    "UnsupportedFormatError",
]

