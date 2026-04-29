from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import lru_cache
from struct import pack, unpack
from typing import Optional
from zoneinfo import ZoneInfo

from loguru import logger
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from zk.attendance import Attendance
from zk import ZK, const

from app.core.config import get_settings

settings = get_settings()
DEVICE_TIMEZONE = ZoneInfo("Asia/Shanghai")
MIN_ATTENDANCE_TIME = datetime(2000, 1, 1, tzinfo=DEVICE_TIMEZONE)
MAX_FUTURE_DRIFT = timedelta(days=365)


def decode_zk_time(data: bytes) -> datetime | None:
    """xFace600 时间戳解码：按 pyzk 原版整数拆分法解析 4 字节小端时间。"""
    if len(data) < 4:
        return None

    try:
        value = unpack("<I", data)[0]
        second = value % 60
        value //= 60
        minute = value % 60
        value //= 60
        hour = value % 24
        value //= 24
        day = value % 31 + 1
        value //= 31
        month = value % 12 + 1
        value //= 12
        year = value + 2000
        return datetime(year, month, day, hour, minute, second)
    except Exception:
        return None


def encode_zk_time(dt: datetime) -> bytes:
    value = (
        (dt.year - 2000) * 12 * 31 * 24 * 3600
        + (dt.month - 1) * 31 * 24 * 3600
        + (dt.day - 1) * 24 * 3600
        + dt.hour * 3600
        + dt.minute * 60
        + dt.second
    )
    return pack("<I", value)


class ZKClientError(Exception):
    pass


class ZKConnectionError(ZKClientError):
    pass


class ZKOperationError(ZKClientError):
    pass


class ZKClient:
    """ZKTeco 设备客户端封装（兼容 pyzk 0.9）"""
    SUPPORTED_ATTENDANCE_RECORD_SIZES = (8, 16, 40, 49)

    def __init__(self, ip: str, port: int = None, timeout: int = None, password: int = 0):
        self.ip = ip
        self.port = port or settings.ZK_DEVICE_PORT
        self.timeout = timeout or settings.ZK_DEVICE_TIMEOUT
        self.password = password
        self.encoding = settings.ZK_DEVICE_ENCODING

    @contextmanager
    def connect(self):
        zk = ZK(
            self.ip,
            port=self.port,
            timeout=self.timeout,
            password=self.password,
            force_udp=False,
            ommit_ping=settings.ZK_DEVICE_OMIT_PING,
            encoding=self.encoding,
        )
        conn = None
        try:
            conn = zk.connect()
            conn.disable_device()
            logger.info(f"ZK 设备 {self.ip} 连接成功")
            yield conn
        except Exception as e:
            logger.error(f"ZK 设备 {self.ip} 连接失败: {e}")
            raise ZKConnectionError(f"设备 {self.ip} 连接失败: {e}")
        finally:
            if conn:
                try:
                    conn.enable_device()
                    conn.disconnect()
                    logger.info(f"ZK 设备 {self.ip} 已断开")
                except Exception as e:
                    logger.warning(f"断开设备 {self.ip} 时出错: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), retry=retry_if_exception_type(ZKOperationError), reraise=True)
    def get_users(self) -> list:
        with self.connect() as conn:
            try:
                return conn.get_users() or []
            except Exception as e:
                logger.error(f"获取用户列表失败: {e}")
                raise ZKOperationError(f"获取用户列表失败: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), retry=retry_if_exception_type(ZKOperationError), reraise=True)
    def save_user(self, uid: int, name: str, privilege: int = 0, password: str = "", group_id: str = "", user_id: str = "", card: int = 0) -> bool:
        with self.connect() as conn:
            try:
                # pyzk 当前版本使用 set_user；保留 save_user 兼容旧调用方。
                user_writer = getattr(conn, "set_user", None) or getattr(conn, "save_user", None)
                if user_writer is None:
                    raise AttributeError("ZK connection does not support set_user/save_user")

                user_writer(
                    uid=uid,
                    name=name,
                    privilege=privilege,
                    password=password,
                    group_id=group_id,
                    user_id=user_id,
                    card=card,
                )
                logger.info(f"用户保存成功: {user_id} (uid={uid})")
                return True
            except Exception as e:
                logger.error(f"保存用户失败: {e}")
                raise ZKOperationError(f"保存用户失败: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), retry=retry_if_exception_type(ZKOperationError), reraise=True)
    def delete_user(self, uid: int) -> bool:
        with self.connect() as conn:
            try:
                conn.delete_user(uid=uid)
                logger.info(f"用户删除成功: uid={uid}")
                return True
            except Exception as e:
                logger.error(f"删除用户失败: {e}")
                raise ZKOperationError(f"删除用户失败: {e}")

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), retry=retry_if_exception_type(ZKOperationError), reraise=True)
    def get_attendance(self) -> list:
        with self.connect() as conn:
            try:
                records = conn.get_attendance() or []
                logger.info(f"获取打卡记录: {len(records)} 条")
                return records
            except Exception as e:
                logger.error(f"获取打卡记录失败: {e}")
                raise ZKOperationError(f"获取打卡记录失败: {e}")

    def get_attendance_safe(self) -> tuple[list, int]:
        with self.connect() as conn:
            try:
                conn.read_sizes()
                if conn.records == 0:
                    return [], 0

                users = conn.get_users()
                attendances = []
                skipped_invalid_count = 0
                attendance_data, size = conn.read_with_buffer(const.CMD_ATTLOG_RRQ)
                if size < 4:
                    logger.warning(f"设备 {self.ip} 未返回打卡记录数据")
                    return [], 0

                total_size = unpack("I", attendance_data[:4])[0]
                full_payload_size = len(attendance_data) - 4
                payload = attendance_data[4 : 4 + total_size]

                if total_size <= 0 or total_size > full_payload_size:
                    logger.warning(
                        f"设备 {self.ip} 打卡记录长度异常: total_size={total_size}, available={full_payload_size}"
                    )
                    return [], 0

                record_size = self._resolve_record_size(payload, conn.records, total_size)
                if record_size is None:
                    logger.warning(
                        f"设备 {self.ip} 无法识别打卡记录格式: records={conn.records}, total_size={total_size}, payload_size={len(payload)}"
                    )
                    return [], 0

                logger.info(
                    f"设备 {self.ip} 打卡缓冲区: records={conn.records}, total_size={total_size}, raw_size={size}, payload_size={len(payload)}, record_size={record_size}"
                )

                if record_size == 8:
                    while len(payload) >= 8:
                        uid, status, timestamp_raw, punch = unpack('HB4sB', payload[:8])
                        payload = payload[8:]
                        timestamp = self._decode_attendance_time(timestamp_raw)
                        if timestamp is None:
                            skipped_invalid_count += 1
                            continue
                        tuser = list(filter(lambda x: x.uid == uid, users))
                        user_id = str(uid) if not tuser else tuser[0].user_id
                        attendances.append(Attendance(user_id, timestamp, status, punch, uid))
                elif record_size == 16:
                    while len(payload) >= 16:
                        user_id, timestamp_raw, status, punch, reserved, workcode = unpack('<I4sBB2sI', payload[:16])
                        payload = payload[16:]
                        timestamp = self._decode_attendance_time(timestamp_raw)
                        if timestamp is None:
                            skipped_invalid_count += 1
                            continue
                        user_id = str(user_id)
                        tuser = list(filter(lambda x: x.user_id == user_id, users))
                        if not tuser:
                            uid = str(user_id)
                            tuser = list(filter(lambda x: x.uid == user_id, users))
                            if tuser:
                                uid = tuser[0].uid
                                user_id = tuser[0].user_id
                        else:
                            uid = tuser[0].uid
                        attendances.append(Attendance(user_id, timestamp, status, punch, uid))
                elif record_size == 40:
                    while len(payload) >= 40:
                        uid, user_id, status, timestamp_raw, punch, space = unpack('<H24sB4sB8s', payload[:40])
                        payload = payload[40:]
                        timestamp = self._decode_attendance_time(timestamp_raw)
                        if timestamp is None:
                            skipped_invalid_count += 1
                            continue
                        user_id = (user_id.split(b'\x00')[0]).decode(errors='ignore')
                        attendances.append(Attendance(user_id, timestamp, status, punch, uid))
                elif record_size == 49:
                    while len(payload) >= 49:
                        uid, user_id, status, timestamp_raw, punch, space, workcode, extra = unpack('<H24sB4sB8sI5s', payload[:49])
                        payload = payload[49:]
                        timestamp = self._decode_attendance_time(timestamp_raw)
                        if timestamp is None:
                            skipped_invalid_count += 1
                            continue
                        user_id = (user_id.split(b'\x00')[0]).decode(errors='ignore')
                        attendances.append(Attendance(user_id, timestamp, status, punch, uid))
                else:
                    logger.warning(f"设备 {self.ip} 未知 record_size={record_size}，跳过解析")

                logger.info(f"获取打卡记录: {len(attendances)} 条，跳过坏记录: {skipped_invalid_count} 条")
                return attendances, skipped_invalid_count
            except Exception as e:
                logger.error(f"获取打卡记录失败: {e}")
                raise ZKOperationError(f"获取打卡记录失败: {e}")

    def _resolve_record_size(self, payload: bytes, record_count: int, total_size: int) -> int | None:
        for size in self.SUPPORTED_ATTENDANCE_RECORD_SIZES:
            if record_count > 0 and total_size == record_count * size:
                return size

        for size in (49, 40, 16, 8):
            if record_count > 0 and total_size >= record_count * size:
                remainder = total_size - record_count * size
                if 0 <= remainder < size:
                    return size

        return None

    @staticmethod
    def _decode_attendance_time(raw_timestamp: bytes) -> Optional[datetime]:
        try:
            decoded = decode_zk_time(raw_timestamp)
            if decoded is None:
                return None

            decoded = decoded.replace(tzinfo=DEVICE_TIMEZONE)
            upper_bound = datetime.now(DEVICE_TIMEZONE) + MAX_FUTURE_DRIFT
            if decoded < MIN_ATTENDANCE_TIME or decoded > upper_bound:
                logger.warning(f"跳过异常打卡时间记录: {decoded.isoformat()}")
                return None
            return decoded
        except Exception as e:
            logger.warning(f"跳过非法打卡时间记录: raw={raw_timestamp.hex()} error={e}")
            return None

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5), retry=retry_if_exception_type(ZKOperationError), reraise=True)
    def unlock(self, time: int = 3) -> bool:
        with self.connect() as conn:
            try:
                conn.unlock(time=time)
                logger.info(f"远程开门成功: 设备={self.ip}, 时长={time}秒")
                return True
            except Exception as e:
                logger.error(f"远程开门失败: {e}")
                raise ZKOperationError(f"远程开门失败: {e}")

    def get_serial_number(self) -> Optional[str]:
        try:
            with self.connect() as conn:
                return conn.get_serialnumber()
        except Exception as e:
            logger.warning(f"获取序列号失败: {e}")
            return None

    def get_device_info(self) -> dict:
        try:
            with self.connect() as conn:
                return {
                    "ip": self.ip,
                    "port": self.port,
                    "serial_number": conn.get_serialnumber(),
                    "firmware_version": conn.get_fp_version() if hasattr(conn, "get_fp_version") else None,
                }
        except Exception as e:
            logger.error(f"获取设备信息失败: {e}")
            return {"ip": self.ip, "status": "unreachable", "error": str(e)}


@lru_cache(maxsize=10)
def get_zk_client(ip: str, port: int = None) -> ZKClient:
    return ZKClient(ip, port)
