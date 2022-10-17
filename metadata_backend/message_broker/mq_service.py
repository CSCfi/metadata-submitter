"""Message Broker Consumer class."""

import json
import ssl
import time
from abc import ABC
from pathlib import Path
from typing import Dict, Union

from aiohttp import web
from amqpstorm import AMQPError, Connection, Message
from jsonschema.exceptions import ValidationError

from ..conf.conf import mq_config
from ..helpers.logger import LOG
from ..helpers.validator import JSONValidator


class MessageBroker(ABC):
    """General Message Broker connection setup."""

    def __init__(
        self,
        vhost: str = "/",
    ) -> None:
        """Consumer init function."""
        self.hostname = mq_config["hostname"]
        self.username = mq_config["username"]
        self.password = mq_config["password"]
        self.port = mq_config["port"]
        self.vhost = vhost
        self.connection = None
        self.max_retries = 5
        self.ssl = mq_config["ssl"]
        context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLSv1_2)
        context.check_hostname = False
        cacertfile = Path(str(mq_config["cacertfile"]))
        certfile = Path(str(mq_config["certfile"]))
        keyfile = Path(str(mq_config["keyfile"]))
        context.verify_mode = ssl.CERT_NONE
        # Require server verification
        if cacertfile.exists():
            context.verify_mode = ssl.CERT_REQUIRED
            context.load_verify_locations(cafile=str(cacertfile))
        # If client verification is required
        if certfile.exists():
            context.load_cert_chain(str(certfile), keyfile=str(keyfile))
        self.ssl_context = {"context": context, "server_hostname": None, "check_hostname": False}

    def _create_connection(self) -> None:
        """Create a connection.

        :return:
        """
        attempts = 0
        while True:
            attempts += 1
            try:
                self.connection = Connection(
                    self.hostname,
                    self.username,
                    self.password,
                    port=self.port,
                    ssl=self.ssl,
                    ssl_options=self.ssl_context,
                    virtual_host=self.vhost,
                )
                LOG.info("Established connection with AMQP server %r", self.connection)
                break
            except AMQPError as error:
                LOG.error("Connection to AMQP server could not be established, error: %r", error)
                if self.max_retries and attempts > self.max_retries:
                    break
                time.sleep(min(attempts * 2, 30))
            except KeyboardInterrupt:
                break

    def _error_message(
        self,
        message: Message,
        error_msg: Dict,
        exchange: str,
        queue: str = "error",
    ) -> None:
        """Send formated error message to error queue."""
        channel = self.connection.channel()  # type: ignore
        properties = {
            "content_type": "application/json",
            "headers": {},
            "correlation_id": message.correlation_id,
            "delivery_mode": 2,
        }

        error = Message.create(channel, error_msg, properties)
        error.publish(queue, exchange)

        channel.close()


class MQPublisher(MessageBroker):
    """Message Broker Publisher class.

    Used for sending messages to a specific vhost and exchange.
    """

    def send_message(
        self, queue: str, exchange: str, message: Dict, json_schema: str, correlation_id: Union[str, None] = None
    ) -> None:
        """Send message."""
        channel = self.connection.channel()  # type: ignore
        # for now we generated correlation_id
        # however we need to figure out if we can get the inbox correlation_id
        # so we can track a file ingestion from inbox to the end
        properties = {
            "content_type": "application/json",
            "headers": {},
            "delivery_mode": 2,
        }
        properties["correlation_id"] = correlation_id if correlation_id else None

        try:
            _content = json.dumps(message)
            JSONValidator(message, json_schema)

            _msg = Message.create(channel, _content, properties)

            _msg.publish(queue, exchange)
            channel.close()
        except ValidationError as error:
            reason = f"Could not validate the ingestion mappings message. Not properly formatted, error: {error}."
            LOG.error(reason)
            raise web.HTTPInternalServerError(reason=reason)


class MQConsumer(MessageBroker):
    """Message Broker Consumer class.

    Used for receiving messages from a specific vhost, exchange and queue.
    ``handle_message`` will have to be handled by subclasses.
    """

    def __init__(self, vhost: str, queue: str, exchange: str) -> None:
        """Get DOI credentials from config."""
        super().__init__(vhost=vhost)
        self.queue = queue
        self.exchange = exchange

    def start(self) -> None:
        """Start the Consumer."""
        if not self.connection:
            self._create_connection()
        while True:
            try:
                channel = self.connection.channel()  # type: ignore
                channel.basic.consume(self, self.queue, no_ack=False)
                LOG.info("Connected to queue: %r", self.queue)
                channel.start_consuming(to_tuple=False)
                if not channel.consumer_tags:
                    channel.close()
            except AMQPError as error:
                LOG.error("Something went wrong: %r", error)
                self._create_connection()
            except KeyboardInterrupt:
                self.connection.close()  # type: ignore
                break

    def handle_message(self, message: Message) -> None:
        """Handle message."""
        return message

    def __call__(self, message: Message) -> None:
        """Process the message body."""
        try:
            self.handle_message(message)
        except (ValidationError, Exception) as error:
            try:
                _msg_error = {
                    "reason": error,
                }
                self._error_message(message, _msg_error, self.exchange, "error")
            except ValidationError:
                LOG.error("Could not validate the error message. Not properly formatted.")
            except Exception as general_error:
                LOG.error(general_error)
            finally:
                message.reject(requeue=False)
        else:
            message.ack()
