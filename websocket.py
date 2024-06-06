import websockets
import json
import logging

from dao.app_dao import does_business_have_mobile_app

LOGGER = logging.getLogger("server")
connected = {}


async def server_func(websocket, path):
    tenant_id = None
    try:
        while True:
            message = await websocket.recv()
            LOGGER.info("message received " + message)
            message = json.loads(message)
            user_id = message.get("user_id")
            enterprise_mobile_app = message.get("enterprise_mobile_app")
            tenant_id = message.get(
                "tenant_id") if not enterprise_mobile_app else "enterprise"
            if tenant_id in connected.keys():
                if user_id in connected[tenant_id].keys():
                    connected[tenant_id][user_id] = websocket
                else:
                    connected[tenant_id] = {user_id: websocket}
            else:
                connected[tenant_id] = {user_id: websocket}

            websocket.id = user_id
            LOGGER.info(f"""
                Websocket connection with
                    User ID {user_id} of
                    Tenant ID {tenant_id}
                connected
            """)

    except websockets.exceptions.ConnectionClosed:
        LOGGER.info(f"Connection closed for User ID {websocket.id}")
        await remove_connection(websocket.id, tenant_id)


async def send_message_to_client(
    key, event_name, data, business_mobile_app, tenant_id=""
):
    try:
        tenant_id = "enterprise" if not business_mobile_app else tenant_id
        if tenant_id in connected.keys() and str(key) in connected[tenant_id].keys():
            websocket = connected[tenant_id][str(key)]
            LOGGER.info({"key": key, "event_name": event_name, "data": data})
            await websocket.send(json.dumps({"event": event_name, "data": data}))
    except Exception as e:
        LOGGER.error(str(e))


async def remove_connection(key, tenant_id):
    try:
        if tenant_id:
            websocket = connected[tenant_id].pop(key)
        return websocket
    except Exception as e:
        LOGGER.error(e)
