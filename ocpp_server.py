import datetime
import json
import aiohttp
from config import config
import logging
from dao import user_dao

LOGGER = logging.getLogger("server")

url = config["OCPP_SERVER_URL"]


async def remote_start(charger_id: str, id_tag: str, connector_id: int, tenant_id: str):
    async with aiohttp.ClientSession() as req:
        try:
            LOGGER.info(f'reaching in remote_start -> charger_id: {charger_id}, id_tag: {id_tag}, connector_id: {connector_id}, tenant_id: {tenant_id}')
            response = await req.post(
                url=url + "chargers/remote_start",
                json={
                    "charger_id": charger_id,
                    "id_tag": id_tag,
                    "connector_id": connector_id
                },
                ssl=False,
                headers={
                    "tenant_id": tenant_id,
                    "Content-type": "json/application"
                }
            )
            data = await response.json()
            if response.status == 200:
                if data["status"] == "Accepted":
                    LOGGER.info(f'returning accepted')
                    return True, ""
            LOGGER.info(f'returning refused')
            return False, "Charger refused to start charging!"
        except Exception as e:
            raise (e)


async def remote_stop(session_id: int, stop_id_tag: str, tenant_id: str):
    async with aiohttp.ClientSession() as req:
        try:
            LOGGER.info(session_id)
            LOGGER.info(stop_id_tag)
            LOGGER.info(tenant_id)
            response = await req.post(
                url=url + "chargers/remote_stop",
                json={
                    "transaction_id": session_id,
                    "stop_id_tag": stop_id_tag
                },
                ssl=False,
                headers={
                    "tenant_id": tenant_id,
                    "Content-type": "json/application"
                }
            )
            data = await response.json()
            LOGGER.info(response.status)
            LOGGER.info(data)
            if response.status == 200:
                if data["status"] == "Accepted":
                    return True, ""
            return False, data["msg"]

        except aiohttp.ClientConnectorError:
            LOGGER.error("""


        ================================================
                Remote stop failed.
                Reasons:
                - Server Url is not valid.
                - Server is not currently active.
        ================================================


            """)
            return False, "Remote stop failed."
        except Exception as e:
            raise e


async def reserve_now(
    user_id: str,
    charger_id: str,
    connector_id: str,
    tenant_id: str,
    expiry_date: datetime
):
    async with aiohttp.ClientSession() as req:
        try:
            id_tag = await user_dao.get_users_id_tag(user_id=user_id)
            response = await req.post(
                url=url + "chargers/reserve_now",
                json={
                    "connector_id": connector_id,
                    "expiry_date": expiry_date,
                    "id_tag": id_tag,
                    "charger_id": charger_id,
                },
                ssl=False,
                headers={
                    "tenant_id": tenant_id,
                    "Content-type": "json/application"
                }
            )
            data = await response.json(content_type="application/json")
            LOGGER.info(response.status)
            LOGGER.info(data)
            if response.status == 200:
                if data["status"] == "Accepted":
                    return True, ""
            return False, data["msg"]
        except Exception as e:
            raise (e)


async def send_phonepe_request(url, payload, headers):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, data=json.dumps({"request": payload}), headers=headers
        ) as response:
            response_data = await response.text()
            return response_data
