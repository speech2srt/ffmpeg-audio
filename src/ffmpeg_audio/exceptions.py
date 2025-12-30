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


class FFmpegStreamError(BaseError):
    """FFmpeg 流式读取错误"""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(message, file_path, returncode, stderr)


class FFmpegSegmentError(BaseError):
    """FFmpeg 片段读取错误"""

    def __init__(
        self,
        message: str,
        file_path: Optional[str] = None,
        returncode: Optional[int] = None,
        stderr: Optional[str] = None,
    ):
        super().__init__(message, file_path, returncode, stderr)
