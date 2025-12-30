# ffmpeg-audio

A Python library for processing audio/video files using FFmpeg with automatic resampling and channel mixing.

## Features

- **Streaming audio reading**: Stream large audio/video files in chunks without loading everything into memory
- **Segment reading**: Read specific time segments from audio files in one operation
- **Automatic resampling**: Automatically resamples audio to 16kHz (fixed)
- **Channel mixing**: Automatically converts to mono channel
- **Format support**: Supports all audio/video formats that FFmpeg supports (MP3, WAV, FLAC, Opus, MP4, etc.)
- **Time range support**: Both streaming and reading support start time and duration parameters

## Installation

```bash
pip install ffmpeg-audio
```

**Note**: This package requires FFmpeg to be installed on your system. Make sure FFmpeg is available in your PATH.

## Quick Start

### Streaming Audio

```python
from ffmpeg_audio import FFmpegAudio
import numpy as np

# Stream entire audio file in chunks
for chunk in FFmpegAudio.stream("audio.mp3"):
    # chunk is a numpy array (float32, range -1.0 ~ 1.0)
    # Process chunk here
    print(f"Chunk shape: {chunk.shape}, dtype: {chunk.dtype}")

# Stream specific time range (from 10s, duration 5s)
for chunk in FFmpegAudio.stream("audio.mp3", start_ms=10000, duration_ms=5000):
    # Process chunk
    pass

# Stream with custom chunk size (1 minute chunks)
for chunk in FFmpegAudio.stream("audio.mp3", chunk_duration_sec=60):
    # Process chunk
    pass
```

### Reading Audio Segments

```python
from ffmpeg_audio import FFmpegAudio

# Read a specific time segment (from 10s to 15s)
audio_data = FFmpegAudio.read(
    file_path="audio.mp3",
    start_ms=10000,  # 10 seconds
    duration_ms=5000,  # 5 seconds
)

# Read from beginning (start_ms defaults to 0)
audio_data = FFmpegAudio.read(
    file_path="audio.mp3",
    duration_ms=5000,  # 5 seconds from start
)

# audio_data is a numpy array (float32, range -1.0 ~ 1.0, 16kHz mono)
print(f"Audio shape: {audio_data.shape}, sample rate: {FFmpegAudio.SAMPLE_RATE} Hz")
```

## API Reference

### FFmpegAudio

Main class for processing audio/video files. All methods are static.

**Constants:**

- `FFmpegAudio.SAMPLE_RATE = 16000`: Output sample rate (Hz)
- `FFmpegAudio.AUDIO_CHANNELS = 1`: Output channel count (mono)
- `FFmpegAudio.STREAM_CHUNK_DURATION_SEC = 1200`: Default chunk duration for streaming (seconds)

#### `FFmpegAudio.stream(file_path, chunk_duration_sec=None, start_ms=None, duration_ms=None)`

Stream audio file in chunks, yielding numpy arrays.

This method reads audio in chunks to minimize memory usage for large files. Each chunk is a numpy array of float32 samples in the range [-1.0, 1.0]. The generator continues until the file ends or the specified duration is reached.

**Parameters:**

- `file_path` (str): Path to the audio/video file (supports all FFmpeg formats)
- `chunk_duration_sec` (int, optional): Duration of each chunk in seconds. Defaults to `STREAM_CHUNK_DURATION_SEC` (1200s = 20 minutes). Must be > 0 if provided.
- `start_ms` (int, optional): Start position in milliseconds. None means from file beginning. If None but `duration_ms` is provided, defaults to 0.
- `duration_ms` (int, optional): Total duration to read in milliseconds. None means read until end. If specified, reading stops when this duration is reached.

**Yields:**

- `np.ndarray`: Audio chunk as float32 array with shape `(n_samples,)`. Values are normalized to [-1.0, 1.0] range.

**Raises:**

- `TypeError`: If parameter types are invalid
- `ValueError`: If `file_path` is empty or parameter values are invalid
- `FFmpegNotFoundError`: If FFmpeg executable is not found in PATH
- `FileNotFoundError`: If the input file does not exist
- `PermissionError`: If file access is denied
- `UnsupportedFormatError`: If file format is not supported or corrupted
- `FFmpegAudioError`: For other FFmpeg processing errors

#### `FFmpegAudio.read(file_path, start_ms=None, duration_ms=None, timeout_ms=300000)`

Read a specific time segment from an audio file in one operation.

This method reads the entire segment into memory at once, suitable for small segments or when the full segment is needed immediately. For large files or streaming use cases, consider using `stream()` instead.

The output format (16kHz mono float32) is optimized for speech processing and energy detection algorithms.

**Parameters:**

- `file_path` (str): Path to audio/video file (supports all FFmpeg formats)
- `start_ms` (int, optional): Start position in milliseconds. None means from beginning. If None but `duration_ms` is provided, defaults to 0.
- `duration_ms` (int, optional): Segment duration in milliseconds. Must be provided (cannot be None together with `start_ms`). If `start_ms` is provided, `duration_ms` is required.
- `timeout_ms` (int, optional): Maximum processing time in milliseconds. Defaults to 300000 (5 minutes). Set to None to disable timeout (not recommended for production).

**Returns:**

- `np.ndarray`: Audio segment as float32 array with shape `(n_samples,)` where `n_samples = duration_ms * SAMPLE_RATE / 1000`
  - dtype: float32
  - value range: [-1.0, 1.0]
  - sample rate: SAMPLE_RATE (16000 Hz)

**Raises:**

- `TypeError`: If parameter types are invalid
- `ValueError`: If parameter values are invalid:
  - `start_ms < 0`
  - `duration_ms <= 0`
  - `timeout_ms <= 0`
  - Both `start_ms` and `duration_ms` are None
  - `start_ms` is provided but `duration_ms` is None
- `FileNotFoundError`: If the input file does not exist
- `FFmpegNotFoundError`: If FFmpeg executable is not found in PATH
- `FFmpegAudioError`: If FFmpeg processing fails or timeout is exceeded

### Exceptions

#### `FFmpegNotFoundError`

Raised when FFmpeg executable is not found in system PATH.

This exception indicates that FFmpeg is either not installed or not accessible from the current environment. Users should install FFmpeg and ensure it's in PATH.

**Attributes:**

- `message`: Human-readable error message describing the issue

#### `FFmpegAudioError`

General FFmpeg audio processing error.

Raised when FFmpeg fails for reasons other than file not found, permission denied, or unsupported format. Contains process return code and stderr for debugging.

**Attributes:**

- `message`: Primary error message (required)
- `file_path`: Path to the file that caused the error (optional)
- `returncode`: FFmpeg process exit code (optional)
- `stderr`: FFmpeg stderr output for debugging (optional)

#### `UnsupportedFormatError`

Raised when audio file format is unsupported or corrupted.

This exception indicates that FFmpeg cannot decode the file, either because the format is not supported or the file is corrupted/invalid.

**Attributes:**

- `message`: Primary error message (required)
- `file_path`: Path to the file that caused the error (optional)
- `returncode`: FFmpeg process exit code (optional)
- `stderr`: FFmpeg stderr output for debugging (optional)

## Requirements

- Python >= 3.10
- FFmpeg (must be installed separately)
- numpy >= 1.26.4

## License

MIT License
