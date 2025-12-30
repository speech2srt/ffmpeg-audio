"""
FFmpeg Audio - A Python library for streaming audio/video files using FFmpeg.

This package provides utilities for:
- Streaming audio/video files in chunks
- Reading specific time segments from audio files
- Automatic resampling and channel mixing
"""

from ffmpeg_audio.audio_segment_reader import AudioSegmentReader
from ffmpeg_audio.audio_streamer import AudioStreamer
from ffmpeg_audio.exceptions import FFmpegNotFoundError, FFmpegSegmentError, FFmpegStreamError

__version__ = "0.1.0"

__all__ = [
    "AudioStreamer",
    "AudioSegmentReader",
    "FFmpegNotFoundError",
    "FFmpegStreamError",
    "FFmpegSegmentError",
]
