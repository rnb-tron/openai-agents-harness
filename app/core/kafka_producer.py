import json
from typing import Any

from app.core.logging import error_logger, get_rid, log_event, proxy_logger

try:
    from aiokafka import AIOKafkaProducer
    from aiokafka.errors import KafkaError
except ImportError:  # pragma: no cover
    AIOKafkaProducer = None
    KafkaError = Exception


class KafkaProducerUtil:
    def __init__(self, bootstrap_servers: str, topic: str, enabled: bool = True):
        self.bootstrap_servers = bootstrap_servers
        self.topic = topic
        self.enabled = enabled
        self.producer = None
        self._started = False

    async def start(self) -> None:
        if not self.enabled or self._started:
            return
        if AIOKafkaProducer is None:
            error_logger.warning("aiokafka is not installed; Kafka disabled")
            self.enabled = False
            return
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda value: json.dumps(value, ensure_ascii=False).encode("utf-8"),
            acks="all",
            request_timeout_ms=10000,
        )
        await self.producer.start()
        self._started = True

    async def send_message(self, message: dict[str, Any], key: str | None = None) -> bool:
        if not self.enabled or not self._started or self.producer is None:
            return False
        payload = dict(message)
        if get_rid() and "rid" not in payload:
            payload["rid"] = get_rid()
        try:
            log_event(proxy_logger, "kafka.producer.send.start", topic=self.topic, key=key)
            await self.producer.send_and_wait(
                self.topic,
                value=payload,
                key=key.encode("utf-8") if key else None,
            )
            return True
        except KafkaError as exc:
            error_logger.error(f"Kafka send failed: {exc}")
            return False

    async def close(self) -> None:
        if self.producer and self._started:
            await self.producer.stop()
            self._started = False


_kafka_producer: KafkaProducerUtil | None = None


async def init_kafka_producer(bootstrap_servers: str, topic: str, enabled: bool = True) -> KafkaProducerUtil:
    global _kafka_producer
    _kafka_producer = KafkaProducerUtil(bootstrap_servers, topic, enabled)
    await _kafka_producer.start()
    return _kafka_producer


def get_kafka_producer() -> KafkaProducerUtil | None:
    return _kafka_producer


async def close_kafka_producer() -> None:
    global _kafka_producer
    if _kafka_producer:
        await _kafka_producer.close()
        _kafka_producer = None
