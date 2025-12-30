"""
FFmpeg Audio Processing Module

Provides utilities for processing audio/video files using FFmpeg subprocess.
Supports both streaming (chunk-by-chunk) and one-time segment reading.
All audio is automatically resampled to 16kHz and converted to mono channel.
"""

import logging
import subprocess
from typing import Iterator, Optional

import numpy as np

from .exceptions import FFmpegAudioError, FFmpegNotFoundError, parse_ffmpeg_error

logger = logging.getLogger(__name__)


class FFmpegAudio:
    """
    FFmpeg-based audio processor for streaming and segment reading.

    All methods are static and process audio/video files using FFmpeg subprocess.
    Output audio is always 16kHz mono float32 format, suitable for speech processing.
    """

    SAMPLE_RATE = 16000  # Output sample rate in Hz
    AUDIO_CHANNELS = 1  # Output channel count (mono)
    STREAM_CHUNK_DURATION_SEC = 1200  # Default chunk duration for streaming (20 minutes)

    @staticmethod
    def stream(
        file_path: str,
        chunk_duration_sec: Optional[int] = None,
        start_ms: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> Iterator[np.ndarray]:
        """
        Stream audio file in chunks, yielding numpy arrays.

        This method reads audio in chunks to minimize memory usage for large files.
        Each chunk is a numpy array of float32 samples in the range [-1.0, 1.0].
        The generator continues until the file ends or the specified duration is reached.

        Args:
            file_path: Path to input audio/video file (supports all FFmpeg formats)
            chunk_duration_sec: Duration of each chunk in seconds. Defaults to
                STREAM_CHUNK_DURATION_SEC (1200s = 20 minutes). Must be > 0 if provided.
            start_ms: Start position in milliseconds. None means from file beginning.
                If None but duration_ms is provided, defaults to 0.
            duration_ms: Total duration to read in milliseconds. None means read until end.
                If specified, reading stops when this duration is reached.

        Yields:
            np.ndarray: Audio chunk as float32 array with shape (n_samples,).
                Values are normalized to [-1.0, 1.0] range.

        Raises:
            TypeError: If parameter types are invalid.
            ValueError: If file_path is empty or parameter values are invalid.
            FFmpegNotFoundError: If FFmpeg executable is not found in PATH.
            FileNotFoundError: If the input file does not exist.
            PermissionError: If file access is denied.
            UnsupportedFormatError: If file format is not supported or corrupted.
            FFmpegAudioError: For other FFmpeg processing errors.
        """
        # Validate parameter types
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError(f"file_path must be a non-empty string, got: {file_path!r}")

        if chunk_duration_sec is not None and not isinstance(chunk_duration_sec, int):
            raise TypeError(f"chunk_duration_sec must be an int or None, got: {type(chunk_duration_sec).__name__}")

        if start_ms is not None and not isinstance(start_ms, int):
            raise TypeError(f"start_ms must be an int or None, got: {type(start_ms).__name__}")

        if duration_ms is not None and not isinstance(duration_ms, int):
            raise TypeError(f"duration_ms must be an int or None, got: {type(duration_ms).__name__}")

        # Validate parameter values
        if start_ms is not None and start_ms < 0:
            raise ValueError(f"start_ms must be >= 0, got {start_ms}")

        if duration_ms is not None and duration_ms <= 0:
            raise ValueError(f"duration_ms must be > 0, got {duration_ms}")

        # Default start_ms to 0 if duration_ms is provided without start_ms
        if start_ms is None and duration_ms is not None:
            logger.warning(f"start_ms is None but duration_ms is provided ({duration_ms}ms). Using default start_ms=0")
            start_ms = 0

        # Apply default chunk duration if not provided or invalid
        if chunk_duration_sec is None:
            chunk_duration_sec = FFmpegAudio.STREAM_CHUNK_DURATION_SEC
        elif chunk_duration_sec <= 0:
            logger.warning(
                f"Invalid `chunk_duration_sec` ({chunk_duration_sec}). Using default: {FFmpegAudio.STREAM_CHUNK_DURATION_SEC}",
            )
            chunk_duration_sec = FFmpegAudio.STREAM_CHUNK_DURATION_SEC

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
        timeout_ms: Optional[int] = 300000,
    ) -> np.ndarray:
        """
        Read a specific time segment from an audio file in one operation.

        This method reads the entire segment into memory at once, suitable for small segments
        or when the full segment is needed immediately. For large files or streaming use cases,
        consider using stream() instead.

        The output format (16kHz mono float32) is optimized for speech processing and energy
        detection algorithms. The sample rate matches SAMPLE_RATE constant.

        Args:
            file_path: Path to audio/video file (supports all FFmpeg formats)
            start_ms: Start position in milliseconds. None means from beginning.
                If None but duration_ms is provided, defaults to 0.
            duration_ms: Segment duration in milliseconds. Must be provided (cannot be None
                together with start_ms). If start_ms is provided, duration_ms is required.
            timeout_ms: Maximum processing time in milliseconds. Defaults to 300000 (5 minutes).
                Set to None to disable timeout (not recommended for production).

        Returns:
            np.ndarray: Audio segment as float32 array with shape (n_samples,).
                - dtype: float32
                - shape: (n_samples,) where n_samples = duration_ms * SAMPLE_RATE / 1000
                - value range: [-1.0, 1.0]
                - sample rate: SAMPLE_RATE (16000 Hz)

        Raises:
            TypeError: If parameter types are invalid.
            ValueError: If parameter values are invalid:
                - start_ms < 0
                - duration_ms <= 0
                - timeout_ms <= 0
                - Both start_ms and duration_ms are None
                - start_ms is provided but duration_ms is None
            FileNotFoundError: If the input file does not exist.
            FFmpegNotFoundError: If FFmpeg executable is not found in PATH.
            FFmpegAudioError: If FFmpeg processing fails or timeout is exceeded.
        """
        # Validate parameter types
        if start_ms is not None and not isinstance(start_ms, int):
            raise TypeError(f"start_ms must be an int or None, got: {type(start_ms).__name__}")

        if duration_ms is not None and not isinstance(duration_ms, int):
            raise TypeError(f"duration_ms must be an int or None, got: {type(duration_ms).__name__}")

        if timeout_ms is not None and not isinstance(timeout_ms, int):
            raise TypeError(f"timeout_ms must be an int or None, got: {type(timeout_ms).__name__}")

        # Validate parameter logic: at least duration_ms must be provided
        if start_ms is None and duration_ms is None:
            raise ValueError("Both start_ms and duration_ms cannot be None. Please specify at least duration_ms.")

        if start_ms is not None and duration_ms is None:
            raise ValueError("duration_ms must be provided when start_ms is specified.")

        # Validate parameter values
        if start_ms is not None and start_ms < 0:
            raise ValueError(f"start_ms must be >= 0, got {start_ms}")

        if duration_ms is not None and duration_ms <= 0:
            raise ValueError(f"duration_ms must be > 0, got {duration_ms}")

        if timeout_ms is not None and timeout_ms <= 0:
            raise ValueError(f"timeout_ms must be > 0, got {timeout_ms}")

        # Default start_ms to 0 if only duration_ms is provided
        if start_ms is None and duration_ms is not None:
            logger.warning(f"start_ms is None but duration_ms is provided ({duration_ms}ms). Using default start_ms=0")
            start_ms = 0

        # Convert milliseconds to seconds for FFmpeg
        start_sec = start_ms / 1000.0
        duration_sec = duration_ms / 1000.0

        # Build FFmpeg command with input seeking for precision
        cmd = ["ffmpeg", "-v", "error"]  # Only show error-level messages

        # Add seeking before -i for input seeking (more precise than output seeking)
        if start_ms is not None:
            cmd.extend(["-ss", str(start_sec)])

        # Add duration limit
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
            timeout_sec = None if timeout_ms is None else timeout_ms / 1000.0
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
