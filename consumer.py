import json
from aio_pika import connect_robust
from aio_pika.abc import AbstractIncomingMessage
from utils import LOGGER
from utils import idle_charging_info_and_send_invoice
from config import config
from service_layers.invoice_layer import consume_and_create_invoice


async def on_message(message: AbstractIncomingMessage) -> None:
    try:
        data = message.body.decode("UTF-8")
        data = json.loads(data)
        session_id = data.get("transaction_id")
        tenant_id = data.get("tenant_id")
        await consume_and_create_invoice(session_id=session_id, tenant_id=tenant_id)
        await message.ack()
    except Exception as e:
        LOGGER.error(e)


async def on_idle_charging_info(message: AbstractIncomingMessage) -> None:
    try:
        data = message.body.decode("UTF-8")
        data = json.loads(data)
        session_id = data.get("transaction_id")
        session_start_time = data.get("session_start_time")
        change_status_time = data.get("change_status_time")
        await idle_charging_info_and_send_invoice(
            session_id=session_id,
            session_start_time=session_start_time,
            change_status_time=change_status_time,
        )
        await message.ack()
    except Exception as e:
        LOGGER.error(e)


async def init_consumer() -> None:
    connection = await connect_robust(
        host=config["RABBITMQ_HOST"],
        login=config["RABBITMQ_USER"],
        password=config["RABBITMQ_PASSWORD"],
        virtualhost=config["RABBITMQ_VIRTUALHOST"],
    )
    channel = await connection.channel()
    queue = await channel.declare_queue(config["RABBITMQ_QUEUE"])
    # queue2 = await channel.declare_queue(config["RABBITMQ_IDLE_CHARGING_QUEUE"])
    await queue.consume(on_message, no_ack=False)
    # await queue2.consume(on_idle_charging_info, no_ack=False)
