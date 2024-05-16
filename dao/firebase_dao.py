from errors.mysql_error import MySQLError
from . import helperdao
import json


async def insert_firebase_notification(
    user_id, session_id, json_data, event_name, tenant_id
):
    try:
        query = f"""
            INSERT INTO `tenant{tenant_id}`.`sent_firebase_notifications`(
                `user_id`,
                `session_id`,
                `event_name`,
                `json`
            ) VALUES(
                '{user_id}',
                '{session_id}',
                '{event_name}',
                '{json.dumps(json_data)}'
            )
        """
        res = await helperdao.upsert_delete(query)
        return res
    except Exception as e:
        raise MySQLError(str(e))


async def get_firebase_notification(user_id, session_id, event_name, tenant_id):
    try:
        query = f"""
            SELECT * FROM `tenant{tenant_id}`.`sent_firebase_notifications` WHERE
            `user_id`='{user_id}' AND `session_id`='{session_id}'
            AND `event_name`='{event_name}'
        """
        res = await helperdao.fetchone_dict(query)
        return res
    except Exception as e:
        raise MySQLError(str(e))


async def delete_firebase_notification(user_id, session_id, tenant_id):
    try:
        query = f"""
            DELETE FROM `tenant{tenant_id}`.`sent_firebase_notifications` WHERE
            `user_id`='{user_id}' AND `session_id`='{session_id}'
        """
        res = await helperdao.upsert_delete(query)
        return res
    except Exception as e:
        raise MySQLError(str(e))


# async def delete_session_notification(session_id):
#     query = f"""
#         DELETE FROM `session_firebase_notifications`
#         WHERE `session_id`='{session_id}'
#     """
#     await helperdao.upsert_delete(query)
#     return


async def get_session_notification(session_id, tenant_id):
    query = f"""
        SELECT
            `notification_type`,
            `notification_value`
        FROM
            `tenant{tenant_id}`.`session_firebase_notifications`
        WHERE `session_id`='{session_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def delete_sent_notification_of_session(session_id, tenant_id):
    query = f"""
        DELETE FROM `tenant{tenant_id}`.`sent_firebase_notifications` WHERE
        `session_id`='{session_id}'
    """
    await helperdao.upsert_delete(query)
    return


async def upsert_notification_config(
    session_id,
    notification_type,
    notification_value,
    tenant_id
):
    try:
        config_exist = await get_session_notification(session_id, tenant_id)
        if not config_exist:
            query = f"""
                INSERT INTO
                    `tenant{tenant_id}`.`session_firebase_notifications`
                    (`session_id`, `notification_type`, `notification_value`)
                VALUES
                ('{session_id}','{notification_type}','{notification_value}')
            """
        else:
            query = f"""
                UPDATE
                    `tenant{tenant_id}`.`session_firebase_notifications`
                SET
                    `notification_type`='{notification_type}',
                    `notification_value`='{notification_value}'
                WHERE `session_id`='{session_id}'
            """
        await helperdao.upsert_delete(query=query)
        return {"msg": "Notification settings are updated successfully."}
    except Exception as e:
        raise MySQLError(str(e))
