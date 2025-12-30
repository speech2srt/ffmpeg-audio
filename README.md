# ffmpeg-audio

A Python library for streaming audio/video files using FFmpeg with automatic resampling and channel mixing.

## Features

- **Streaming audio reading**: Stream large audio/video files in chunks without loading everything into memory
- **Automatic resampling**: Automatically resamples audio to 16kHz (configurable)
- **Channel mixing**: Automatically converts to mono channel
- **Segment reading**: Read specific time segments from audio files
- **Format support**: Supports all audio/video formats that FFmpeg supports (MP3, WAV, FLAC, Opus, MP4, etc.)

## Installation

```bash
pip install ffmpeg-audio
```

**Note**: This package requires FFmpeg to be installed on your system. Make sure FFmpeg is available in your PATH.

## Quick Start

### Streaming Audio

```python
from ffmpeg_audio import AudioStreamer
import numpy as np

# Stream audio file in chunks
for chunk in AudioStreamer.stream("audio.mp3"):
    # chunk is a numpy array (float32, range -1.0 ~ 1.0)
    # Process chunk here
    print(f"Chunk shape: {chunk.shape}, dtype: {chunk.dtype}")
```

### Reading Audio Segments

```python
from ffmpeg_audio import AudioSegmentReader

# Read a specific time segment (from 10s to 15s)
audio_data = AudioSegmentReader.read(
    file_path="audio.mp3",
    start_ms=10000,  # 10 seconds
    duration_ms=5000,  # 5 seconds
)

# audio_data is a numpy array (float32, range -1.0 ~ 1.0, 16kHz mono)
print(f"Audio shape: {audio_data.shape}, sample rate: {AudioSegmentReader.SAMPLE_RATE} Hz")
```

## API Reference

### AudioStreamer

Main class for streaming audio/video files.

#### `AudioStreamer.stream(file_path, chunk_duration_sec=None)`

Stream audio file in chunks.

**Parameters:**

- `file_path` (str): Path to the audio/video file
- `chunk_duration_sec` (int, optional): Duration of each chunk in seconds. Defaults to 1200 (20 minutes).

**Yields:**

- `np.ndarray`: Audio chunk as float32 numpy array (range -1.0 ~ 1.0, 16kHz mono)

**Raises:**

- `TypeError`: If `chunk_duration_sec` is not an int or None
- `ValueError`: If `file_path` is empty or invalid
- `FFmpegNotFoundError`: If FFmpeg is not installed or not in PATH
- `FileNotFoundError`: If the audio file does not exist
- `PermissionError`: If permission is denied accessing the file
- `UnsupportedFormatError`: If the file format is not supported or invalid
- `FFmpegAudioError`: If FFmpeg process fails (for other errors)

**Constants:**

- `AudioStreamer.SAMPLE_RATE = 16000`: Output sample rate (Hz)
- `AudioStreamer.AUDIO_CHANNELS = 1`: Output channel count (mono)
- `AudioStreamer.STREAM_CHUNK_DURATION_SEC = 1200`: Default chunk duration (seconds)

### AudioSegmentReader

Class for reading specific time segments from audio files.

#### `AudioSegmentReader.read(file_path, start_ms, duration_ms)`

Read a specific time segment from an audio file.

**Parameters:**

- `file_path` (str): Path to the audio/video file
- `start_ms` (int): Start time in milliseconds (must be >= 0)
- `duration_ms` (int): Duration in milliseconds (must be > 0)

**Returns:**

- `np.ndarray`: Audio data as float32 numpy array (range -1.0 ~ 1.0, 16kHz mono)

**Raises:**

- `FileNotFoundError`: If file doesn't exist
- `ValueError`: If time parameters are invalid
- `FFmpegNotFoundError`: If FFmpeg is not installed or not in PATH
- `FFmpegAudioError`: If FFmpeg processing fails

**Constants:**

- `AudioSegmentReader.SAMPLE_RATE = 16000`: Output sample rate (Hz)

### Exceptions

#### `FFmpegNotFoundError`

Raised when FFmpeg is not installed or not available in PATH.

**Attributes:**

- `message`: Error message

#### `FFmpegAudioError`

Raised when FFmpeg audio processing fails.

**Attributes:**

- `message`: Error message
- `file_path`: Path to the file that caused the error (optional)
- `returncode`: FFmpeg process return code (optional)
- `stderr`: FFmpeg standard error output (optional)

#### `UnsupportedFormatError`

Raised when the audio file format is not supported or contains invalid data.

**Attributes:**

- `message`: Error message
- `file_path`: Path to the file that caused the error (optional)
- `returncode`: FFmpeg process return code (optional)
- `stderr`: FFmpeg standard error output (optional)

## Requirements

- Python >= 3.10
- FFmpeg (must be installed separately)
- numpy >= 1.26.4

## License

MIT License

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
