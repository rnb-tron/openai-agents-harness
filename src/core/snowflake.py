import threading
import time


class SnowflakeIdGenerator:
    def __init__(self, worker_id: int = 1, datacenter_id: int = 1):
        self.epoch = 1704067200000
        self.worker_id_bits = 5
        self.datacenter_id_bits = 5
        self.sequence_bits = 12
        self.max_worker_id = (1 << self.worker_id_bits) - 1
        self.max_datacenter_id = (1 << self.datacenter_id_bits) - 1
        self.max_sequence = (1 << self.sequence_bits) - 1
        self.worker_id_shift = self.sequence_bits
        self.datacenter_id_shift = self.sequence_bits + self.worker_id_bits
        self.timestamp_shift = self.sequence_bits + self.worker_id_bits + self.datacenter_id_bits
        if worker_id > self.max_worker_id or worker_id < 0:
            raise ValueError(f"worker_id must be between 0 and {self.max_worker_id}")
        if datacenter_id > self.max_datacenter_id or datacenter_id < 0:
            raise ValueError(f"datacenter_id must be between 0 and {self.max_datacenter_id}")
        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()

    def _get_timestamp(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp: int) -> int:
        timestamp = self._get_timestamp()
        while timestamp <= last_timestamp:
            timestamp = self._get_timestamp()
        return timestamp

    def generate_id(self) -> int:
        with self.lock:
            timestamp = self._get_timestamp()
            if timestamp < self.last_timestamp:
                raise RuntimeError("Clock moved backwards")
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.max_sequence
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0
            self.last_timestamp = timestamp
            return (
                ((timestamp - self.epoch) << self.timestamp_shift)
                | (self.datacenter_id << self.datacenter_id_shift)
                | (self.worker_id << self.worker_id_shift)
                | self.sequence
            )


_snowflake_generator: SnowflakeIdGenerator | None = None


def get_snowflake_generator() -> SnowflakeIdGenerator:
    global _snowflake_generator
    if _snowflake_generator is None:
        _snowflake_generator = SnowflakeIdGenerator()
    return _snowflake_generator


def generate_rid() -> str:
    return str(get_snowflake_generator().generate_id())
