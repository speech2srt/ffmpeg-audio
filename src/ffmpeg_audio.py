"""
FFmpeg Audio Processing Module

Provides utilities for processing audio/video files using FFmpeg subprocess.
Supports both streaming (chunk-by-chunk) and one-time segment reading.
All audio is automatically resampled to 16kHz and converted to mono channel.
"""

import logging
import os
import subprocess
from typing import Iterator, Optional

import numpy as np

from .exceptions import FFmpegAudioError, FFmpegNotFoundError, parse_ffmpeg_error

logger = logging.getLogger(__name__)


def _get_stream_chunk_duration_sec() -> int:
    """Get stream chunk duration from environment variable, compatible with non-standard values, defaults to 1200 seconds"""
    env_val = os.getenv("FFMPEG_STREAM_CHUNK_DURATION_SEC", "").strip()
    if not env_val:
        return 1200
    try:
        value = int(env_val)
        return value if value > 0 else 1200
    except (ValueError, TypeError):
        return 1200


def _get_default_timeout_ms() -> int:
    """Get default timeout from environment variable, compatible with non-standard values, defaults to 300000 milliseconds (5 minutes)"""
    env_val = os.getenv("FFMPEG_TIMEOUT_MS", "").strip()
    if not env_val:
        return 300000
    try:
        value = int(env_val)
        return value if value > 0 else 300000
    except (ValueError, TypeError):
        return 300000


# Module-level constants (can be used in function parameter defaults)
_STREAM_CHUNK_DURATION_SEC = _get_stream_chunk_duration_sec()
_DEFAULT_TIMEOUT_MS = _get_default_timeout_ms()


class FFmpegAudio:
    """
    FFmpeg-based audio processor for streaming and segment reading.

    All methods are static and process audio/video files using FFmpeg subprocess.
    Output audio is always 16kHz mono float32 format, suitable for speech processing.
    """

    SAMPLE_RATE = 16000  # Output sample rate in Hz
    AUDIO_CHANNELS = 1  # Output channel count (mono)

    @staticmethod
    def stream(
        file_path: str,
        start_ms: Optional[int] = None,
        duration_ms: Optional[int] = None,
        chunk_duration_sec: int = _STREAM_CHUNK_DURATION_SEC,
    ) -> Iterator[np.ndarray]:
        """
        Stream audio file in chunks, yielding numpy arrays.

        This method reads audio in chunks to minimize memory usage for large files.
        Each chunk is a numpy array of float32 samples in the range [-1.0, 1.0].
        The generator continues until the file ends or the specified duration is reached.

        Args:
            file_path: Path to input audio/video file (supports all FFmpeg formats)
            start_ms: Start position in milliseconds. None means from file beginning.
            duration_ms: Total duration to read in milliseconds. None means read until end.
                If specified, reading stops when this duration is reached.
            chunk_duration_sec: Duration of each chunk in seconds. Defaults to 1200s (20 minutes, configurable via FFMPEG_STREAM_CHUNK_DURATION_SEC env var).
                If <= 0, uses default with a warning.

        Yields:
            np.ndarray: Audio chunk as float32 array with shape (n_samples,).
                Values are normalized to [-1.0, 1.0] range.

        Raises:
            TypeError: If parameter types are invalid.
            ValueError: If file_path is empty or parameter values are invalid (after auto-correction):
                - start_ms < 0 (auto-corrected to None)
                - duration_ms <= 0 (auto-corrected to None)
            FFmpegNotFoundError: If FFmpeg executable is not found in PATH.
            FileNotFoundError: If the input file does not exist.
            PermissionError: If file access is denied.
            UnsupportedFormatError: If file format is not supported or corrupted.
            FFmpegAudioError: For other FFmpeg processing errors.
        """
        # Validate parameter types
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError(f"file_path must be a non-empty string, got: {file_path!r}")

        if not isinstance(chunk_duration_sec, int):
            raise TypeError(f"chunk_duration_sec must be an int, got: {type(chunk_duration_sec).__name__}")

        if start_ms is not None and not isinstance(start_ms, int):
            raise TypeError(f"start_ms must be an int or None, got: {type(start_ms).__name__}")

        if duration_ms is not None and not isinstance(duration_ms, int):
            raise TypeError(f"duration_ms must be an int or None, got: {type(duration_ms).__name__}")

        # Validate and auto-correct parameter values
        # If start_ms < 0, set to None (will read from beginning)
        if start_ms is not None and start_ms < 0:
            logger.warning(f"start_ms is negative ({start_ms}ms), setting to None. Will read from beginning of file.")
            start_ms = None

        # If duration_ms <= 0, set to None (will read to end)
        if duration_ms is not None and duration_ms <= 0:
            logger.warning(f"duration_ms is invalid ({duration_ms}ms), setting to None. Will read to end of file.")
            duration_ms = None

        # Auto-correct invalid chunk duration
        if chunk_duration_sec <= 0:
            logger.warning(
                f"Invalid `chunk_duration_sec` ({chunk_duration_sec}). Using default: {_STREAM_CHUNK_DURATION_SEC}",
            )
            chunk_duration_sec = _STREAM_CHUNK_DURATION_SEC

        # Build FFmpeg command
        # Using list form (not shell string) to avoid injection vulnerabilities
        cmd = ["ffmpeg", "-v", "error"]  # Only show error-level messages

        # Add seeking parameters before -i for better precision (input seeking)
        # Placing -ss before -i makes FFmpeg seek in the input file, which is faster
        if start_ms is not None:
            start_sec = start_ms / 1000.0
            cmd.extend(["-ss", str(start_sec)])

        # Add duration limit if specified
        if duration_ms is not None:
            duration_sec = duration_ms / 1000.0
            cmd.extend(["-t", str(duration_sec)])

        # Add input file and audio processing parameters
        cmd.extend(
            [
                "-i",
                file_path,
                "-vn",  # No video (extract audio only)
                "-sn",  # No subtitles
                "-dn",  # No data streams
                "-ar",
                str(FFmpegAudio.SAMPLE_RATE),  # Resample to 16kHz (required for speech models)
                "-ac",
                str(FFmpegAudio.AUDIO_CHANNELS),  # Convert to mono (downmix if stereo)
                "-f",
                "s16le",  # 16-bit signed little-endian PCM (raw audio format)
                "-",  # Output to stdout for streaming
            ]
        )

        # Launch FFmpeg subprocess
        process: Optional[subprocess.Popen] = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,  # Capture stderr for error parsing
                bufsize=10**7,  # 10MB buffer for efficient I/O
            )
        except FileNotFoundError:
            # FileNotFoundError from Popen means FFmpeg executable not found
            raise FFmpegNotFoundError("FFmpeg not found. Please ensure FFmpeg is installed and available in PATH.")

        # Calculate chunk size: samples per chunk * 2 bytes per sample (16-bit)
        chunk_size = int(chunk_duration_sec * FFmpegAudio.SAMPLE_RATE)
        bytes_per_chunk = chunk_size * 2

        # Track total samples read if duration limit is specified
        total_read_samples = 0
        total_duration_samples = None
        if duration_ms is not None:
            total_duration_samples = int((duration_ms / 1000.0) * FFmpegAudio.SAMPLE_RATE)

        try:
            while True:
                # Check if process has terminated (poll() returns returncode or None)
                if process.poll() is not None:
                    # Process finished, check for errors
                    if process.returncode != 0:
                        stderr_output = process.stderr.read().decode("utf-8", errors="ignore")
                        raise parse_ffmpeg_error(stderr_output, file_path, process.returncode)
                    # Normal termination, no more data
                    break

                # Stop if duration limit reached
                if total_duration_samples is not None and total_read_samples >= total_duration_samples:
                    break

                # Calculate how many bytes to read this iteration
                # May be less than bytes_per_chunk if approaching duration limit
                read_bytes = bytes_per_chunk
                if total_duration_samples is not None:
                    remaining_samples = total_duration_samples - total_read_samples
                    remaining_bytes = remaining_samples * 2
                    if remaining_bytes < read_bytes:
                        read_bytes = remaining_bytes

                # Read raw PCM bytes from FFmpeg stdout
                raw_bytes = process.stdout.read(read_bytes)

                # EOF reached (no more data)
                if not raw_bytes:
                    break

                # Convert raw bytes to int16 array (zero-copy operation)
                # frombuffer creates a view without copying data, very efficient
                audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16)

                # Track progress for duration limiting
                total_read_samples += len(audio_int16)

                # Normalize int16 [-32768, 32767] to float32 [-1.0, 1.0]
                # This format is standard for audio processing libraries
                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                yield audio_float32

        finally:
            # Ensure subprocess is properly cleaned up
            if process:
                # Close pipes to release resources
                try:
                    process.stdout.close()
                    process.stderr.close()
                except Exception:
                    pass
                # Terminate process if still running
                try:
                    process.kill()
                except Exception:
                    pass
                # Wait for termination (with timeout to avoid hanging)
                try:
                    process.wait(timeout=1)
                except Exception:
                    pass

                # Final error check: if process terminated with error, raise exception
                # This catches errors that might have occurred after the main loop
                if process.returncode is not None and process.returncode != 0:
                    try:
                        stderr_output = process.stderr.read().decode("utf-8", errors="ignore")
                    except Exception:
                        stderr_output = ""
                    raise parse_ffmpeg_error(stderr_output, file_path, process.returncode)

    @staticmethod
    def read(
        file_path: str,
        start_ms: Optional[int] = None,
        duration_ms: Optional[int] = None,
        timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    ) -> np.ndarray:
        """
        Read audio data from a file in one operation.

        This method reads audio data into memory at once. If both start_ms and duration_ms
        are None, it reads the entire file. For large files or streaming use cases,
        consider using stream() instead.

        The output format (16kHz mono float32) is optimized for speech processing and energy
        detection algorithms. The sample rate matches SAMPLE_RATE constant.

        Args:
            file_path: Path to audio/video file (supports all FFmpeg formats)
            start_ms: Start position in milliseconds. None means from beginning.
                If both start_ms and duration_ms are None, reads the entire file.
            duration_ms: Segment duration in milliseconds. None means read until end of file.
                If start_ms is provided but duration_ms is None, reads from start_ms to end of file.
                If both start_ms and duration_ms are None, reads the entire file.
            timeout_ms: Maximum processing time in milliseconds. Defaults to 300000ms (5 minutes, configurable via FFMPEG_TIMEOUT_MS env var).
                - If <= 0, uses default timeout with a warning.
                - If > 0, uses the specified value.
                - To disable timeout, explicitly pass a very large value (not recommended for production).

        Returns:
            np.ndarray: Audio data as float32 array with shape (n_samples,).
                - dtype: float32
                - shape: (n_samples,) where n_samples depends on the audio duration
                - value range: [-1.0, 1.0]
                - sample rate: SAMPLE_RATE (16000 Hz)

        Raises:
            TypeError: If parameter types are invalid.
            ValueError: If parameter values are invalid (after auto-correction):
                - start_ms < 0 (auto-corrected to None)
                - duration_ms <= 0 (auto-corrected to None)
                - timeout_ms <= 0 (auto-corrected to default timeout)
            FileNotFoundError: If the input file does not exist.
            FFmpegNotFoundError: If FFmpeg executable is not found in PATH.
            FFmpegAudioError: If FFmpeg processing fails or timeout is exceeded.
        """
        # Validate parameter types
        if start_ms is not None and not isinstance(start_ms, int):
            raise TypeError(f"start_ms must be an int or None, got: {type(start_ms).__name__}")

        if duration_ms is not None and not isinstance(duration_ms, int):
            raise TypeError(f"duration_ms must be an int or None, got: {type(duration_ms).__name__}")

        if not isinstance(timeout_ms, int):
            raise TypeError(f"timeout_ms must be an int, got: {type(timeout_ms).__name__}")

        # Validate parameter logic
        # If start_ms is specified but duration_ms is None, warn and allow reading to end of file
        if start_ms is not None and duration_ms is None:
            logger.warning(f"start_ms is specified ({start_ms}ms) but duration_ms is None. " "Will read from start_ms to end of file.")

        # Validate and auto-correct parameter values
        # If start_ms < 0, set to None (will read from beginning)
        if start_ms is not None and start_ms < 0:
            logger.warning(f"start_ms is negative ({start_ms}ms), setting to None. Will read from beginning of file.")
            start_ms = None

        # If duration_ms <= 0, set to None (will read to end)
        if duration_ms is not None and duration_ms <= 0:
            logger.warning(f"duration_ms is invalid ({duration_ms}ms), setting to None. Will read to end of file.")
            duration_ms = None

        # Handle timeout_ms: auto-correct invalid values
        # If timeout_ms <= 0, use default timeout with warning
        if timeout_ms <= 0:
            logger.warning(f"timeout_ms is invalid ({timeout_ms}ms), using default value {_DEFAULT_TIMEOUT_MS}ms.")
            timeout_ms = _DEFAULT_TIMEOUT_MS
        # else: timeout_ms > 0, use the specified value

        # Convert milliseconds to seconds for FFmpeg (only if provided)
        start_sec = start_ms / 1000.0 if start_ms is not None else None
        duration_sec = duration_ms / 1000.0 if duration_ms is not None else None

        # Build FFmpeg command with input seeking for precision
        cmd = ["ffmpeg", "-v", "error"]  # Only show error-level messages

        # Add seeking before -i for input seeking (more precise than output seeking)
        # Only add -ss if start_ms is specified
        if start_ms is not None:
            cmd.extend(["-ss", str(start_sec)])

        # Add duration limit only if duration_ms is specified
        # If both are None, FFmpeg will read the entire file
        if duration_ms is not None:
            cmd.extend(["-t", str(duration_sec)])

        # Add input file and audio processing parameters
        cmd.extend(
            [
                "-i",
                file_path,
                "-vn",  # No video (audio extraction only)
                "-sn",  # No subtitles
                "-dn",  # No data streams
                "-ar",
                str(FFmpegAudio.SAMPLE_RATE),  # Resample to 16kHz (standard for speech processing)
                "-ac",
                "1",  # Convert to mono (downmix stereo to mono)
                "-f",
                "s16le",  # 16-bit signed little-endian PCM (raw audio format)
                "-",  # Output to stdout for reading
            ]
        )

        # Launch FFmpeg subprocess
        process = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**7,  # 10MB buffer for efficient I/O
            )
        except FileNotFoundError:
            # FileNotFoundError from Popen indicates FFmpeg executable not found
            raise FFmpegNotFoundError("FFmpeg not found. Please ensure FFmpeg is installed and available in PATH.")

        try:
            # Read all output in one operation (blocking until complete or timeout)
            timeout_sec = timeout_ms / 1000.0
            raw_bytes, stderr_bytes = process.communicate(timeout=timeout_sec)

            # Check for FFmpeg errors
            if process.returncode != 0:
                stderr_output = stderr_bytes.decode("utf-8", errors="ignore")
                raise parse_ffmpeg_error(stderr_output, file_path, process.returncode)

            # Handle empty output (e.g., segment beyond file duration)
            if not raw_bytes:
                return np.array([], dtype=np.float32)

            # Convert raw PCM bytes to int16 array (zero-copy view)
            audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16)

            # Normalize int16 [-32768, 32767] to float32 [-1.0, 1.0]
            # Standard audio processing format
            audio_float32 = audio_int16.astype(np.float32) / 32768.0

            return audio_float32

        except subprocess.TimeoutExpired:
            # Timeout occurred, kill process and raise error
            if process:
                process.kill()
            raise FFmpegAudioError(
                f"FFmpeg timeout while processing {file_path}",
                file_path=file_path,
            )
        finally:
            # Ensure proper cleanup of subprocess resources
            if process:
                # Close pipes
                try:
                    process.stdout.close()
                    process.stderr.close()
                except Exception:
                    pass
                # Terminate if still running
                try:
                    process.kill()
                except Exception:
                    pass
                # Wait for termination
                try:
                    process.wait(timeout=1)
                except Exception:
                    pass

                # Final error check: catch any errors that occurred during cleanup
                # This provides additional robustness beyond communicate() error handling
                if process.returncode is not None and process.returncode != 0:
                    try:
                        stderr_output = process.stderr.read().decode("utf-8", errors="ignore")
                    except Exception:
                        stderr_output = ""
                    raise parse_ffmpeg_error(stderr_output, file_path, process.returncode)
