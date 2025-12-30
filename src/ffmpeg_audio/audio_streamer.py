"""
FFmpeg 音频流类

使用 ffmpeg 子进程流式读取任意音频/视频文件，
并在读取过程中自动完成重采样(16k)和声道混合(mono)。
"""

import logging
import subprocess
from typing import Iterator, Optional

import numpy as np
from ffmpeg_audio.exceptions import FFmpegNotFoundError, parse_ffmpeg_error

logger = logging.getLogger(__name__)


class AudioStreamer:
    """
    使用 ffmpeg 子进程流式读取任意音频/视频文件，
    并在读取过程中自动完成重采样(16k)和声道混合(mono)。
    """

    SAMPLE_RATE = 16000
    AUDIO_CHANNELS = 1
    STREAM_CHUNK_DURATION_SEC = 1200  # 流式读取 chunk 时长（20分钟）

    @staticmethod
    def stream(
        file_path: str,
        chunk_duration_sec: Optional[int] = None,
    ) -> Iterator[np.ndarray]:
        """
        静态方法：流式读取音频文件，yield numpy array (float32)

        Args:
            file_path: 输入音频/视频文件路径（本地挂载路径）
            chunk_duration_sec: 每次读取的音频时长（秒），默认使用 STREAM_CHUNK_DURATION_SEC

        Yields:
            np.ndarray: 音频数据块（float32，范围 -1.0 ~ 1.0）

        Raises:
            TypeError: chunk_duration_sec 类型错误时抛出
            ValueError: file_path 为空或无效时抛出
            FFmpegNotFoundError: FFmpeg 未安装或不在 PATH 中时抛出
            FileNotFoundError: 文件不存在时抛出
            PermissionError: 文件权限不足时抛出
            UnsupportedFormatError: 文件格式不支持时抛出
            FFmpegAudioError: FFmpeg 进程失败时抛出
        """
        # 参数验证
        if not isinstance(file_path, str) or not file_path.strip():
            raise ValueError(f"file_path must be a non-empty string, got: {file_path!r}")

        if chunk_duration_sec is not None and not isinstance(chunk_duration_sec, int):
            raise TypeError(f"chunk_duration_sec must be an int or None, got: {type(chunk_duration_sec).__name__}")

        # 使用默认值如果未提供或无效
        if chunk_duration_sec is None:
            chunk_duration_sec = AudioStreamer.STREAM_CHUNK_DURATION_SEC
        elif chunk_duration_sec <= 0:
            logger.warning(
                f"Invalid `chunk_duration_sec` ({chunk_duration_sec}). Using default: {AudioStreamer.STREAM_CHUNK_DURATION_SEC}",
            )
            chunk_duration_sec = AudioStreamer.STREAM_CHUNK_DURATION_SEC

        # 构建 ffmpeg 命令（不使用 shlex，直接使用列表形式）
        # -i input: 输入文件
        # -vn: 禁用视频流
        # -sn: 禁用字幕流
        # -dn: 禁用数据流
        # -ar 16000: 重采样到 16k
        # -ac 1: 混合为单声道
        # -f s16le: 输出格式为 16位 原始 PCM (Little Endian)
        # -: 输出到 stdout
        cmd = [
            "ffmpeg",
            "-v",
            "error",  # 只输出错误信息
            "-i",
            file_path,
            "-vn",  # 禁用视频流
            "-sn",  # 禁用字幕流
            "-dn",  # 禁用数据流
            "-ar",
            str(AudioStreamer.SAMPLE_RATE),  # 重采样到 16kHz（FSMN-VAD 模型固定要求）
            "-ac",
            str(AudioStreamer.AUDIO_CHANNELS),  # 混合为单声道
            "-f",
            "s16le",  # 输出格式为 16-bit PCM (Little Endian)
            "-",  # 输出到 stdout
        ]

        # 启动子进程
        process: Optional[subprocess.Popen] = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,  # 捕获 stderr 以便 debug
                bufsize=10**7,  # 设置一个合理的缓冲区
            )
        except FileNotFoundError:
            raise FFmpegNotFoundError("FFmpeg not found. Please ensure FFmpeg is installed and available in PATH.")

        # 计算每次读取的字节数：采样点数 * 2 (16-bit = 2 bytes)
        chunk_size = int(chunk_duration_sec * AudioStreamer.SAMPLE_RATE)
        bytes_per_chunk = chunk_size * 2

        try:
            while True:
                # 检查进程状态（如果进程已终止，poll() 返回返回码，否则返回 None）
                if process.poll() is not None:
                    # 进程已终止，检查是否有错误
                    if process.returncode != 0:
                        stderr_output = process.stderr.read().decode("utf-8", errors="ignore")
                        raise parse_ffmpeg_error(stderr_output, file_path, process.returncode)
                    # 进程正常结束，退出循环
                    break

                # 从 pipe 读取原始字节
                raw_bytes = process.stdout.read(bytes_per_chunk)

                if not raw_bytes:
                    break

                # 字节转 int16 numpy 数组
                # frombuffer 是零拷贝的，非常快
                audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16)

                # 归一化到 float32 (-1.0 ~ 1.0)
                # funasr 内部通常接受 float 输入，或者 int16 也可以
                # 转换为 float32 是最稳妥的通用做法
                audio_float32 = audio_int16.astype(np.float32) / 32768.0

                yield audio_float32

        finally:
            # 清理子进程资源
            if process:
                try:
                    process.stdout.close()
                    process.stderr.close()
                except Exception:
                    pass
                try:
                    process.kill()
                except Exception:
                    pass
                try:
                    process.wait(timeout=1)
                except Exception:
                    pass

                # 检查是否有错误（仅在进程已终止时检查）
                if process.returncode is not None and process.returncode != 0:
                    try:
                        stderr_output = process.stderr.read().decode("utf-8", errors="ignore")
                    except Exception:
                        stderr_output = ""
                    raise parse_ffmpeg_error(stderr_output, file_path, process.returncode)
