import logging
from dao import firebase_dao
import fcm

LOGGER = logging.getLogger("server")


async def send_firebase_notification_if_not_sent(
    user_id, session_id, data, title, body, event_name, tenant_id
):
    try:
        notification_exist = await firebase_dao.get_firebase_notification(
            user_id=user_id,
            session_id=session_id,
            event_name=event_name,
            tenant_id=tenant_id
        )
        if not notification_exist:
            await fcm.send_notification(
                title=title, body=body, user_id=user_id, data=data, tenant_id=tenant_id
            )
            await firebase_dao.insert_firebase_notification(
                user_id=user_id,
                session_id=session_id,
                event_name=event_name,
                tenant_id=tenant_id,
                json_data={
                    "title": title,
                    "body": body,
                    "user_id": user_id,
                    "data": data,
                },
            )
        return
    except Exception as e:
        LOGGER.error(e)
