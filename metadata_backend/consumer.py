"""Message Broker Consumer."""

import os

from .helpers.logger import LOG
from .message_broker.mq_service import MQConsumer


def main() -> None:
    """Launch the Message Broker Consumer."""
    _vhost = str(os.environ.get("BROKER_VHOST"))
    _queue = str(os.environ.get("BROKER_QUEUE"))
    _exchange = str(os.environ.get("BROKER_EXCHANGE"))
    mq_consumer = MQConsumer(_vhost, _queue, _exchange)
    mq_consumer.start()
    LOG.info("Started RabbitMQ consumer for vhost: %s, exchange: %s on queue %s", _vhost, _exchange, _queue)


if __name__ == "__main__":
    main()
