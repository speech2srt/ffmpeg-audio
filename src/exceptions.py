"""
Exception classes for FFmpeg audio processing errors.

Provides a hierarchy of exceptions for different error conditions,
enabling precise error handling and debugging.
"""

from typing import Optional


class FFmpegNotFoundError(Exception):
    """
    Raised when FFmpeg executable is not found in system PATH.

    This exception indicates that FFmpeg is either not installed or not accessible
    from the current environment. Users should install FFmpeg and ensure it's in PATH.
    """

    def __init__(self, message: str):
        """
        Initialize exception.

        Args:
            message: Human-readable error message describing the issue.
        """
        super().__init__(message)
        self.message = message


class BaseError(Exception):
    """
    Base exception class for FFmpeg processing errors.

    Provides common attributes for error context: file path, process return code,
    and stderr output. All FFmpeg-related exceptions inherit from this class.
    """

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ):
        """
        Initialize exception with error context.

        Args:
            message: Primary error message (required).
            file_path: Path to the file that caused the error (optional).
            returncode: FFmpeg process exit code (optional).
            stderr: FFmpeg stderr output for debugging (optional).
        """
        super().__init__(message)
        self.message = message
        self.file_path = file_path
        self.returncode = returncode
        self.stderr = stderr


class FFmpegAudioError(BaseError):
    """
    General FFmpeg audio processing error.

    Raised when FFmpeg fails for reasons other than file not found, permission denied,
    or unsupported format. Contains process return code and stderr for debugging.
    """

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(message, file_path, returncode, stderr)


class UnsupportedFormatError(BaseError):
    """
    Raised when audio file format is unsupported or corrupted.

    This exception indicates that FFmpeg cannot decode the file, either because
    the format is not supported or the file is corrupted/invalid.
    """

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(message, file_path, returncode, stderr)


def parse_ffmpeg_error(
    stderr: str,
    file_path: str,
    returncode: int,
) -> Exception:
    """
    Parse FFmpeg stderr to determine error type and return appropriate exception.

    Analyzes FFmpeg error messages to map generic process failures to specific
    Python exceptions, improving error handling and user experience.

    Args:
        stderr: FFmpeg standard error output (may contain error messages).
        file_path: Path to the file being processed.
        returncode: FFmpeg process exit code (non-zero indicates error).

    Returns:
        Exception object of the appropriate type:
        - FileNotFoundError: File does not exist
        - PermissionError: Access denied
        - UnsupportedFormatError: Format not supported or corrupted
        - FFmpegAudioError: Other FFmpeg errors
    """
    stderr_lower = stderr.lower()

    # Check for specific error patterns in stderr
    if "no such file or directory" in stderr_lower:
        return FileNotFoundError(f"Audio file not found: {file_path}")
    elif "permission denied" in stderr_lower:
        return PermissionError(f"Permission denied accessing file: {file_path}")
    elif "invalid data found when processing input" in stderr_lower:
        return UnsupportedFormatError(
            f"Unsupported or invalid audio format: {file_path}",
            file_path=file_path,
            returncode=returncode,
            stderr=stderr,
        )
    else:
        # Fallback to generic FFmpeg error for unrecognized error patterns
        return FFmpegAudioError(
            f"FFmpeg process failed with return code {returncode}",
            file_path=file_path,
            returncode=returncode,
            stderr=stderr,
        )
