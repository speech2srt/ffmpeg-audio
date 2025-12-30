"""
FFmpeg 音频处理类

使用 ffmpeg 子进程处理音频/视频文件，支持流式读取和片段读取。
自动完成重采样(16k)和声道混合(mono)。
"""

import logging
import subprocess
from typing import Iterator, Optional

import numpy as np

from .exceptions import FFmpegAudioError, FFmpegNotFoundError, parse_ffmpeg_error

logger = logging.getLogger(__name__)


class FFmpegAudio:
    """
    使用 ffmpeg 子进程处理音频/视频文件，支持流式读取和片段读取。
    自动完成重采样(16k)和声道混合(mono)。
    """

    SAMPLE_RATE = 16000
    AUDIO_CHANNELS = 1
    STREAM_CHUNK_DURATION_SEC = 1200  # 流式读取 chunk 时长（20分钟）

    @staticmethod
    def stream(
        file_path: str,
        chunk_duration_sec: Optional[int] = None,
        start_ms: Optional[int] = None,
        duration_ms: Optional[int] = None,
    ) -> Iterator[np.ndarray]:
        """
        静态方法：流式读取音频文件，yield numpy array (float32)

        Args:
            file_path: 输入音频/视频文件路径（本地挂载路径）
            chunk_duration_sec: 每次读取的音频时长（秒），默认使用 STREAM_CHUNK_DURATION_SEC
            start_ms: 开始时间（毫秒），默认为 None（从文件开头开始）
            duration_ms: 总读取时长（毫秒），默认为 None（读取到文件结束）
                如果 start_ms 为 None 但 duration_ms 不为 None，则 start_ms 默认为 0

        Yields:
            np.ndarray: 音频数据块（float32，范围 -1.0 ~ 1.0）

        Raises:
            TypeError: chunk_duration_sec 类型错误时抛出
            ValueError: file_path 为空或无效时抛出，或 start_ms/duration_ms 无效时抛出
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

        if start_ms is not None and not isinstance(start_ms, int):
            raise TypeError(f"start_ms must be an int or None, got: {type(start_ms).__name__}")

        if duration_ms is not None and not isinstance(duration_ms, int):
            raise TypeError(f"duration_ms must be an int or None, got: {type(duration_ms).__name__}")

        # 参数值验证
        if start_ms is not None and start_ms < 0:
            raise ValueError(f"start_ms must be >= 0, got {start_ms}")

        if duration_ms is not None and duration_ms <= 0:
            raise ValueError(f"duration_ms must be > 0, got {duration_ms}")

        # 处理 start_ms 和 duration_ms 的逻辑
        if start_ms is None and duration_ms is not None:
            # 如果 start_ms 缺失但有 duration_ms，则 start_ms 默认为 0
            logger.warning(f"start_ms is None but duration_ms is provided ({duration_ms}ms). Using default start_ms=0")
            start_ms = 0

        # 使用默认值如果未提供或无效
        if chunk_duration_sec is None:
            chunk_duration_sec = FFmpegAudio.STREAM_CHUNK_DURATION_SEC
        elif chunk_duration_sec <= 0:
            logger.warning(
                f"Invalid `chunk_duration_sec` ({chunk_duration_sec}). Using default: {FFmpegAudio.STREAM_CHUNK_DURATION_SEC}",
            )
            chunk_duration_sec = FFmpegAudio.STREAM_CHUNK_DURATION_SEC

        # 构建 ffmpeg 命令（不使用 shlex，直接使用列表形式）
        # -ss: 开始时间（秒），如果指定了 start_ms
        # -t: 持续时间（秒），如果指定了 duration_ms
        # -i input: 输入文件
        # -vn: 禁用视频流
        # -sn: 禁用字幕流
        # -dn: 禁用数据流
        # -ar 16000: 重采样到 16k
        # -ac 1: 混合为单声道
        # -f s16le: 输出格式为 16位 原始 PCM (Little Endian)
        # -: 输出到 stdout
        cmd = ["ffmpeg", "-v", "error"]  # 只输出错误信息

        # 添加开始时间参数（在 -i 之前，输入前定位更精确）
        if start_ms is not None:
            start_sec = start_ms / 1000.0
            cmd.extend(["-ss", str(start_sec)])

        # 添加持续时间参数
        if duration_ms is not None:
            duration_sec = duration_ms / 1000.0
            cmd.extend(["-t", str(duration_sec)])

        # 添加输入文件和其他参数
        cmd.extend(
            [
                "-i",
                file_path,
                "-vn",  # 禁用视频流
                "-sn",  # 禁用字幕流
                "-dn",  # 禁用数据流
                "-ar",
                str(FFmpegAudio.SAMPLE_RATE),  # 重采样到 16kHz（FSMN-VAD 模型固定要求）
                "-ac",
                str(FFmpegAudio.AUDIO_CHANNELS),  # 混合为单声道
                "-f",
                "s16le",  # 输出格式为 16-bit PCM (Little Endian)
                "-",  # 输出到 stdout
            ]
        )

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
        chunk_size = int(chunk_duration_sec * FFmpegAudio.SAMPLE_RATE)
        bytes_per_chunk = chunk_size * 2

        # 如果指定了 duration_ms，需要跟踪已读取的时长
        total_read_samples = 0
        total_duration_samples = None
        if duration_ms is not None:
            total_duration_samples = int((duration_ms / 1000.0) * FFmpegAudio.SAMPLE_RATE)

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

                # 如果指定了 duration_ms，检查是否已达到总时长
                if total_duration_samples is not None and total_read_samples >= total_duration_samples:
                    break

                # 从 pipe 读取原始字节
                # 如果指定了 duration_ms，可能需要读取更少的字节
                read_bytes = bytes_per_chunk
                if total_duration_samples is not None:
                    remaining_samples = total_duration_samples - total_read_samples
                    remaining_bytes = remaining_samples * 2
                    if remaining_bytes < read_bytes:
                        read_bytes = remaining_bytes

                raw_bytes = process.stdout.read(read_bytes)

                if not raw_bytes:
                    break

                # 字节转 int16 numpy 数组
                # frombuffer 是零拷贝的，非常快
                audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16)

                # 更新已读取的采样点数
                total_read_samples += len(audio_int16)

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

    @staticmethod
    def read(
        file_path: str,
        start_ms: Optional[int] = None,
        duration_ms: Optional[int] = None,
        timeout_ms: Optional[int] = 300000,
    ) -> np.ndarray:
        """
        读取音频文件的指定时间段（一次性读取）

        使用 FFmpeg 提取指定时间段的音频，自动重采样到 16kHz 并转换为单声道。
        返回的数据格式可直接用于能量检测算法（如 find_best_cut_point）。
        采样率固定为 SAMPLE_RATE，调用能量检测函数时直接传入 SAMPLE_RATE 即可。

        Args:
            file_path: 音频文件路径（支持所有 FFmpeg 支持的格式）
            start_ms: 开始时间（毫秒），默认为 None（如果 duration_ms 提供则默认为 0）
            duration_ms: 持续时间（毫秒），默认为 None（必须提供，不能与 start_ms 同时为 None）
            timeout_ms: 超时时间（毫秒），默认为 300000（5分钟），None 表示不限制超时

        Returns:
            np.ndarray: 音频数据
                - dtype: float32
                - 形状: (n_samples,)
                - 数值范围: -1.0 ~ 1.0
                - 采样率: 固定为 SAMPLE_RATE (16000 Hz)

        Raises:
            TypeError: start_ms、duration_ms 或 timeout_ms 类型错误时抛出
            ValueError: 时间参数无效时抛出
                - start_ms < 0
                - duration_ms <= 0
                - timeout_ms <= 0
                - 两者都为 None
                - start_ms 不为 None 但 duration_ms 为 None
            FileNotFoundError: 文件不存在
            FFmpegNotFoundError: FFmpeg 未安装或不在 PATH 中时抛出
            FFmpegAudioError: FFmpeg 处理失败或超时
        """
        # 类型验证
        if start_ms is not None and not isinstance(start_ms, int):
            raise TypeError(f"start_ms must be an int or None, got: {type(start_ms).__name__}")

        if duration_ms is not None and not isinstance(duration_ms, int):
            raise TypeError(f"duration_ms must be an int or None, got: {type(duration_ms).__name__}")

        if timeout_ms is not None and not isinstance(timeout_ms, int):
            raise TypeError(f"timeout_ms must be an int or None, got: {type(timeout_ms).__name__}")

        # 逻辑验证
        if start_ms is None and duration_ms is None:
            raise ValueError("Both start_ms and duration_ms cannot be None. Please specify at least duration_ms.")

        if start_ms is not None and duration_ms is None:
            raise ValueError("duration_ms must be provided when start_ms is specified.")

        # 参数值验证
        if start_ms is not None and start_ms < 0:
            raise ValueError(f"start_ms must be >= 0, got {start_ms}")

        if duration_ms is not None and duration_ms <= 0:
            raise ValueError(f"duration_ms must be > 0, got {duration_ms}")

        if timeout_ms is not None and timeout_ms <= 0:
            raise ValueError(f"timeout_ms must be > 0, got {timeout_ms}")

        # 处理 start_ms 和 duration_ms 的逻辑
        if start_ms is None and duration_ms is not None:
            # 如果 start_ms 缺失但有 duration_ms，则 start_ms 默认为 0
            logger.warning(f"start_ms is None but duration_ms is provided ({duration_ms}ms). Using default start_ms=0")
            start_ms = 0

        # 转换为秒
        start_sec = start_ms / 1000.0
        duration_sec = duration_ms / 1000.0

        # 构建 FFmpeg 命令
        # -ss: 开始时间（秒），如果指定了 start_ms
        # -t: 持续时间（秒），如果指定了 duration_ms
        # -i: 输入文件
        # -vn: 禁用视频流
        # -sn: 禁用字幕流
        # -dn: 禁用数据流
        # -ar: 采样率
        # -ac: 声道数（1=单声道，2=立体声）
        # -f s16le: 输出格式为 16 位 PCM（小端序）
        # -: 输出到标准输出
        cmd = ["ffmpeg", "-v", "error"]  # 只输出错误信息

        # 添加开始时间参数（在 -i 之前，输入前定位更精确）
        if start_ms is not None:
            cmd.extend(["-ss", str(start_sec)])

        # 添加持续时间参数
        if duration_ms is not None:
            cmd.extend(["-t", str(duration_sec)])

        # 添加输入文件和其他参数
        cmd.extend(
            [
                "-i",
                file_path,
                "-vn",  # 禁用视频流
                "-sn",  # 禁用字幕流
                "-dn",  # 禁用数据流
                "-ar",
                str(FFmpegAudio.SAMPLE_RATE),  # 重采样到目标采样率（能量检测算法标准要求）
                "-ac",
                "1",  # 单声道（能量检测算法标准要求）
                "-f",
                "s16le",  # 输出格式为 16 位 PCM（小端序）
                "-",  # 输出到标准输出
            ]
        )

        # 启动 FFmpeg 子进程
        process = None
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=10**7,  # 设置合理的缓冲区大小（10MB）
            )
        except FileNotFoundError:
            # subprocess.Popen 的 FileNotFoundError 表示 FFmpeg 命令未找到
            raise FFmpegNotFoundError("FFmpeg not found. Please ensure FFmpeg is installed and available in PATH.")

        try:
            # 读取所有输出数据（等待进程完成）
            # 转换超时时间为秒（如果提供了超时时间）
            timeout_sec = None if timeout_ms is None else timeout_ms / 1000.0
            raw_bytes, stderr_bytes = process.communicate(timeout=timeout_sec)

            # 检查进程返回码
            if process.returncode != 0:
                stderr_output = stderr_bytes.decode("utf-8", errors="ignore")
                raise parse_ffmpeg_error(stderr_output, file_path, process.returncode)

            # 如果没有读取到数据，返回空数组
            if not raw_bytes:
                return np.array([], dtype=np.float32)

            # 将原始字节转换为 int16 numpy 数组
            # frombuffer 是零拷贝操作，性能很高
            audio_int16 = np.frombuffer(raw_bytes, dtype=np.int16)

            # 归一化到 float32 格式（范围 -1.0 ~ 1.0）
            # int16 范围是 -32768 ~ 32767，除以 32768.0 得到 -1.0 ~ 1.0 的浮点数
            audio_float32 = audio_int16.astype(np.float32) / 32768.0

            return audio_float32

        except subprocess.TimeoutExpired:
            if process:
                process.kill()
            raise FFmpegAudioError(
                f"FFmpeg timeout while processing {file_path}",
                file_path=file_path,
            )
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
                # 虽然 communicate() 已等待完成，但为了一致性和健壮性，这里也检查
                if process.returncode is not None and process.returncode != 0:
                    try:
                        stderr_output = process.stderr.read().decode("utf-8", errors="ignore")
                    except Exception:
                        stderr_output = ""
                    raise parse_ffmpeg_error(stderr_output, file_path, process.returncode)
