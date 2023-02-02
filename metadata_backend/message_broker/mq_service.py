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

from ..api.operators.file import FileOperator
from ..conf.conf import create_db_client, mq_config
from ..helpers.logger import LOG
from ..helpers.validator import JSONValidator


class MessageBroker(ABC):
    """General Message Broker connection setup."""

    def __init__(
        self,
    ) -> None:
        """Consumer init function."""
        self.hostname = mq_config["hostname"]
        self.username = mq_config["username"]
        self.password = mq_config["password"]
        self.port = mq_config["port"]
        self.connection = None
        self.ssl = mq_config["ssl"]
        context = ssl.SSLContext(protocol=ssl.PROTOCOL_TLSv1_2)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        if self.ssl:
            cacertfile = Path(str(mq_config["cacertfile"]))
            certfile = Path(str(mq_config["certfile"]))
            keyfile = Path(str(mq_config["keyfile"]))
            # Require server verification
            if cacertfile.exists():
                context.verify_mode = ssl.CERT_REQUIRED
                context.load_verify_locations(cafile=str(cacertfile))
            # If client verification is required
            if certfile.exists():
                context.load_cert_chain(str(certfile), keyfile=str(keyfile))
        self.ssl_context = {"context": context, "server_hostname": None, "check_hostname": False}

    def _error_message(
        self, error_msg: Dict, vhost: str, exchange: str, queue: str = "error", correlation_id: Union[str, None] = None
    ) -> None:
        """Send formated error message to error queue."""
        properties = {
            "content_type": "application/json",
            "headers": {},
            "delivery_mode": 2,
        }

        if correlation_id:
            properties["correlation_id"] = correlation_id

        with Connection(
            self.hostname,
            self.username,
            self.password,
            port=self.port,
            ssl=self.ssl,
            ssl_options=self.ssl_context,
            virtual_host=vhost,
        ) as connection:
            channel = connection.channel()  # type: ignore

            error = Message.create(channel, error_msg, properties)
            error.publish(queue, exchange)
            channel.close()


class MQPublisher(MessageBroker):
    """Message Broker Publisher class.

    Used for sending messages to a specific vhost and exchange.
    """

    def send_message(
        self,
        vhost: str,
        queue: str,
        exchange: str,
        message: Dict,
        json_schema: str,
        correlation_id: Union[str, None] = None,
    ) -> None:
        """Send message."""
        # we need to figure out if we can get the inbox correlation_id
        # so we can track a file ingestion from inbox to the end
        # for now we only add it if we know it
        properties = {
            "content_type": "application/json",
            "headers": {},
            "delivery_mode": 2,
        }
        if correlation_id:
            properties["correlation_id"] = correlation_id

        with Connection(
            self.hostname,
            self.username,
            self.password,
            port=self.port,
            ssl=self.ssl,
            ssl_options=self.ssl_context,
            virtual_host=vhost,
        ) as connection:
            channel = connection.channel()  # type: ignore

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
        super().__init__()
        self.queue = queue
        self.exchange = exchange
        self.max_retries = 5
        self.vhost = vhost
        self.db_client = create_db_client()

    def _create_connection(self) -> None:
        """Create a connection."""
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

    async def handle_message(self, message: Message) -> None:
        """Handle message."""
        # TO_DO: adjust for real code
        file_operator = FileOperator(self.db_client)
        content = json.loads(message.body)
        if content["operation"] == "upload":
            await file_operator.create_file_or_version(content["data"])
        elif content["operation"] == "remove":
            await file_operator.flag_file_deleted(content["filepath"])
        else:
            LOG.error("Un-identified inbox operation.")

    async def __call__(self, message: Message) -> None:
        """Process the message body."""
        try:
            await self.handle_message(message)
        except (ValidationError, Exception) as error:
            try:
                _msg_error = {
                    "reason": error,
                }
                self._error_message(_msg_error, self.exchange, "error", message.correlation_id)
            except ValidationError:
                LOG.error("Could not validate the error message. Not properly formatted.")
            except Exception as general_error:
                LOG.error(general_error)
            finally:
                message.reject(requeue=False)
        else:
            message.ack()
