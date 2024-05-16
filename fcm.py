import logging
from dao import user_dao
from async_firebase import AsyncFirebaseClient

LOGGER = logging.getLogger("server")
# client = AsyncFirebaseClient()
# client.creds_from_service_account_file("iotrics-config.json")

config_dict = {
    "63c42daf-1219-424b-8b5e-294e6c29604c": "echarge-config.json",
    "681bd0fe-ae63-4bda-aa83-229fcda207c2": "wheelsdrive-config.json",
    "a4989bb4-a835-4093-a418-cd4c2b9a10c4": "charger911-config.json",
    "2c9893fe-8853-43f4-9fdd-9403e3bb316f": "sock8-prod-firebase-adminsdk.json",
    "fa14e7c0-4aac-41d5-b373-fb1d45ff06a9": "evplug-prod.json"
}


async def send_notification(title, body, user_id, data=None, tenant_id=None):
    if tenant_id and user_id:
        res = await user_dao.get_device_token(user_id, tenant_id)
        device_token = res.get("token")
        os = res.get("os", None)
        if os == "ios":
            await send_ios_notification(title, body, device_token, tenant_id, data)
        elif os == "android":
            await send_android_notification(title, body, device_token, tenant_id, data)
    # return


async def send_ios_notification(title, body, device_token, tenant_id, data):
    try:
        client = getFirebaseClient(tenant_id)
        ios_config = client.build_apns_config(
            priority="high",
            ttl=2419200,
            # apns_topic="io.powerpump.newapp",
            collapse_key="push",
            alert=body,
            title=title,
            badge=1,
            custom_data=data,
        )
        await client.push(device_token=device_token, apns=ios_config)
    except KeyError:
        LOGGER.error("Missing Firebase Config")
    except Exception as e:
        LOGGER.error(e)


async def send_android_notification(title, body, device_token, tenant_id, data):
    try:
        client = getFirebaseClient(tenant_id)
        android_config = client.build_android_config(
            priority="high",
            ttl=2419200,
            collapse_key="push",
            body=body,
            title=title,
            data=data,
        )

        await client.push(device_token=device_token, android=android_config)
    except KeyError:
        LOGGER.error("Missing Firebase Config")
    except Exception as e:
        LOGGER.error(e)


def getFirebaseClient(tenant_id):
    try:
        client = AsyncFirebaseClient()
        client.creds_from_service_account_file(config_dict[tenant_id])
        return client
    except KeyError as e:
        raise e
