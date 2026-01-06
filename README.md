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

## Configuration

### Environment Variables

The library supports configuration through environment variables:

- `FFMPEG_STREAM_CHUNK_DURATION_SEC`: Default chunk duration (in seconds) for streaming operations. If not set or invalid, defaults to 1200 seconds (20 minutes). The value must be a positive integer. Non-standard values (empty strings, non-numeric strings, negative numbers, or zero) will fall back to the default value.

- `FFMPEG_TIMEOUT_MS`: Default timeout (in milliseconds) for read operations. If not set or invalid, defaults to 300000 milliseconds (5 minutes). The value must be a positive integer. Non-standard values will fall back to the default value.

**Example:**

```bash
# Set default chunk duration to 5 minutes (300 seconds)
export FFMPEG_STREAM_CHUNK_DURATION_SEC=300

# Use in Python
from ffmpeg_audio import FFmpegAudio

# Will use 300 seconds as default chunk duration
for chunk in FFmpegAudio.stream("audio.mp3"):
    # Process chunk
    pass
```

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

# Read from beginning (5 seconds from start)
audio_data = FFmpegAudio.read(
    file_path="audio.mp3",
    duration_ms=5000,  # 5 seconds from start
)

# Read entire file (no start_ms or duration_ms specified)
audio_data = FFmpegAudio.read(file_path="audio.mp3")

# audio_data is a numpy array (float32, range -1.0 ~ 1.0, 16kHz mono)
print(f"Audio shape: {audio_data.shape}, sample rate: {FFmpegAudio.SAMPLE_RATE} Hz")
```

## API Reference

### FFmpegAudio

Main class for processing audio/video files. All methods are static.

**Constants:**

- `FFmpegAudio.SAMPLE_RATE = 16000`: Output sample rate (Hz)
- `FFmpegAudio.AUDIO_CHANNELS = 1`: Output channel count (mono)

#### `FFmpegAudio.stream(file_path, start_ms=None, duration_ms=None, chunk_duration_sec=<default>)`

Stream audio file in chunks, yielding numpy arrays.

This method reads audio in chunks to minimize memory usage for large files. Each chunk is a numpy array of float32 samples in the range [-1.0, 1.0]. The generator continues until the file ends or the specified duration is reached.

**Parameters:**

- `file_path` (str): Path to the audio/video file (supports all FFmpeg formats)
- `start_ms` (int, optional): Start position in milliseconds. None means from file beginning. If < 0, will be auto-corrected to None with a warning.
- `duration_ms` (int, optional): Total duration to read in milliseconds. None means read until end. If <= 0, will be auto-corrected to None with a warning.
- `chunk_duration_sec` (int): Duration of each chunk in seconds. Defaults to 1200s (20 minutes), configurable via `FFMPEG_STREAM_CHUNK_DURATION_SEC` environment variable. If <= 0, will be auto-corrected to default with a warning.

**Yields:**

- `np.ndarray`: Audio chunk as float32 array with shape `(n_samples,)`. Values are normalized to [-1.0, 1.0] range.

**Raises:**

- `TypeError`: If parameter types are invalid
- `ValueError`: If `file_path` is empty or parameter values are invalid (after auto-correction):
  - `start_ms < 0` (auto-corrected to None)
  - `duration_ms <= 0` (auto-corrected to None)
- `FFmpegNotFoundError`: If FFmpeg executable is not found in PATH
- `FileNotFoundError`: If the input file does not exist
- `PermissionError`: If file access is denied
- `UnsupportedFormatError`: If file format is not supported or corrupted
- `FFmpegAudioError`: For other FFmpeg processing errors

#### `FFmpegAudio.read(file_path, start_ms=None, duration_ms=None, timeout_ms=<default>)`

Read audio data from a file in one operation.

This method reads audio data into memory at once. If both `start_ms` and `duration_ms` are None, it reads the entire file. For large files or streaming use cases, consider using `stream()` instead.

The output format (16kHz mono float32) is optimized for speech processing and energy detection algorithms.

**Parameters:**

- `file_path` (str): Path to audio/video file (supports all FFmpeg formats)
- `start_ms` (int, optional): Start position in milliseconds. None means from beginning. If < 0, will be auto-corrected to None with a warning. If specified but `duration_ms` is None, reads from `start_ms` to end of file.
- `duration_ms` (int, optional): Segment duration in milliseconds. None means read until end of file. If <= 0, will be auto-corrected to None with a warning. If `start_ms` is provided but `duration_ms` is None, reads from `start_ms` to end of file. If both are None, reads the entire file.
- `timeout_ms` (int): Maximum processing time in milliseconds. Defaults to 300000ms (5 minutes), configurable via `FFMPEG_TIMEOUT_MS` environment variable. If <= 0, will be auto-corrected to default with a warning.

**Returns:**

- `np.ndarray`: Audio data as float32 array with shape `(n_samples,)` where `n_samples` depends on the audio duration
  - dtype: float32
  - value range: [-1.0, 1.0]
  - sample rate: SAMPLE_RATE (16000 Hz)

**Raises:**

- `TypeError`: If parameter types are invalid
- `ValueError`: If parameter values are invalid (after auto-correction):
  - `start_ms < 0` (auto-corrected to None)
  - `duration_ms <= 0` (auto-corrected to None)
  - `timeout_ms <= 0` (auto-corrected to default timeout)
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
