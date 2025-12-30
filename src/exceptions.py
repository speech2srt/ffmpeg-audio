"""
异常类定义

提供统一的异常接口，便于错误处理和调试。
"""

from typing import Optional


class FFmpegNotFoundError(Exception):
    """FFmpeg 未找到错误 - 当系统未安装 FFmpeg 或 FFmpeg 不在 PATH 中时抛出"""

    def __init__(self, message: str):
        """
        初始化异常

        Args:
            message: 错误消息
        """
        super().__init__(message)
        self.message = message


class BaseError(Exception):
    """基础异常类，提供统一的异常接口"""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ):
        """
        初始化异常

        Args:
            message: 错误消息（必选）
            file_path: 文件路径（可选）
            returncode: FFmpeg 进程返回码（可选）
            stderr: FFmpeg 标准错误输出（可选）
        """
        super().__init__(message)
        self.message = message
        self.file_path = file_path
        self.returncode = returncode
        self.stderr = stderr


class FFmpegAudioError(BaseError):
    """FFmpeg 音频处理错误"""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(message, file_path, returncode, stderr)


class UnsupportedFormatError(BaseError):
    """不支持的音频格式错误 - 当文件格式无法被 FFmpeg 解码时抛出"""

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
    从 FFmpeg stderr 解析错误类型并返回对应的异常

    Args:
        stderr: FFmpeg 标准错误输出
        file_path: 文件路径
        returncode: FFmpeg 进程返回码

    Returns:
        对应的异常对象
    """
    stderr_lower = stderr.lower()

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
        # 其他错误使用 FFmpegAudioError
        return FFmpegAudioError(
            f"FFmpeg process failed with return code {returncode}",
            file_path=file_path,
            returncode=returncode,
            stderr=stderr,
        )
