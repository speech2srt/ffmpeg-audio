"""
FFmpeg Audio - A Python library for streaming audio/video files using FFmpeg.

This package provides utilities for:
- Streaming audio/video files in chunks
- Reading specific time segments from audio files
- Automatic resampling and channel mixing
"""

import logging

from ffmpeg_audio.audio_segment_reader import AudioSegmentReader
from ffmpeg_audio.audio_streamer import AudioStreamer
from ffmpeg_audio.exceptions import FFmpegNotFoundError, FFmpegSegmentError, FFmpegStreamError

__version__ = "0.1.0"

# 配置库的根 logger
# 使用 NullHandler 确保库在用户未配置日志时保持静默
# 如果用户配置了日志（如 logging.basicConfig()），日志会向上冒泡到根 logger 被处理
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

__all__ = [
    "AudioStreamer",
    "AudioSegmentReader",
    "FFmpegNotFoundError",
    "FFmpegStreamError",
    "FFmpegSegmentError",
]
