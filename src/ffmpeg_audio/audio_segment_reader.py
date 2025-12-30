"""
音频片段读取工具

使用 FFmpeg 从音频文件中读取指定时间段的音频数据，用于能量检测等算法。
支持所有 FFmpeg 支持的音频/视频格式（包括 Opus、MP3、WAV、FLAC 等）。
"""

import logging
import subprocess

import numpy as np
from ffmpeg_audio.exceptions import FFmpegNotFoundError, FFmpegSegmentError

logger = logging.getLogger(__name__)


class AudioSegmentReader:
    """音频片段读取器，提供静态方法读取指定时间段的音频数据"""

    # 采样率常量（能量检测算法标准要求）
    SAMPLE_RATE = 16000

    @staticmethod
    def read(
        file_path: str,
        start_ms: int,
        duration_ms: int,
    ) -> np.ndarray:
        """
        读取音频文件的指定时间段

        使用 FFmpeg 提取指定时间段的音频，自动重采样到 16kHz 并转换为单声道。
        返回的数据格式可直接用于能量检测算法（如 find_best_cut_point）。
        采样率固定为 SAMPLE_RATE，调用能量检测函数时直接传入 SAMPLE_RATE 即可。

        Args:
            file_path: 音频文件路径（支持所有 FFmpeg 支持的格式）
            start_ms: 开始时间（毫秒）
            duration_ms: 持续时间（毫秒）

        Returns:
            np.ndarray: 音频数据
                - dtype: float32
                - 形状: (n_samples,)
                - 数值范围: -1.0 ~ 1.0
                - 采样率: 固定为 SAMPLE_RATE (16000 Hz)

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 时间参数无效（start_ms < 0 或 duration_ms <= 0）
            FFmpegNotFoundError: FFmpeg 未安装或不在 PATH 中时抛出
            FFmpegSegmentError: FFmpeg 处理失败
        """
        # 参数验证
        if start_ms < 0:
            raise ValueError(f"start_ms must be >= 0, got {start_ms}")
        if duration_ms <= 0:
            raise ValueError(f"duration_ms must be > 0, got {duration_ms}")

        # 转换为秒
        start_sec = start_ms / 1000.0
        duration_sec = duration_ms / 1000.0

        # 构建 FFmpeg 命令
        # -ss: 开始时间（秒）
        # -t: 持续时间（秒）
        # -i: 输入文件
        # -vn: 禁用视频流
        # -sn: 禁用字幕流
        # -dn: 禁用数据流
        # -ar: 采样率
        # -ac: 声道数（1=单声道，2=立体声）
        # -f s16le: 输出格式为 16 位 PCM（小端序）
        # -: 输出到标准输出
        cmd = [
            "ffmpeg",
            "-v",
            "error",  # 只输出错误信息
            "-ss",
            str(start_sec),  # 开始时间（秒）
            "-t",
            str(duration_sec),  # 持续时间（秒）
            "-i",
            file_path,
            "-vn",  # 禁用视频流
            "-sn",  # 禁用字幕流
            "-dn",  # 禁用数据流
            "-ar",
            str(AudioSegmentReader.SAMPLE_RATE),  # 重采样到目标采样率（能量检测算法标准要求）
            "-ac",
            "1",  # 单声道（能量检测算法标准要求）
            "-f",
            "s16le",  # 输出格式为 16 位 PCM（小端序）
            "-",  # 输出到标准输出
        ]

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
            raw_bytes, stderr_bytes = process.communicate()

            # 检查进程返回码
            if process.returncode != 0:
                stderr_output = stderr_bytes.decode("utf-8", errors="ignore")
                raise FFmpegSegmentError(
                    f"FFmpeg failed with return code {process.returncode}",
                    file_path=file_path,
                    returncode=process.returncode,
                    stderr=stderr_output,
                )

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

        except FileNotFoundError as e:
            # 这里的 FileNotFoundError 是文件系统层面的错误（文件不存在）
            # 与 subprocess.Popen 的 FileNotFoundError（FFmpeg 未找到）不同
            raise FileNotFoundError(f"Audio file not found: {file_path}") from e
        except subprocess.TimeoutExpired:
            if process:
                process.kill()
            raise FFmpegSegmentError(
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
