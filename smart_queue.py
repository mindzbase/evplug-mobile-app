import asyncio
from datetime import datetime, timedelta
import logging
import time
from queue_model import QueueModel
import fcm
import ocpp_server
LOGGER = logging.getLogger("server")


location_queue_list = {}

location_queue_skipped_list = {}

location_task_list = {}


def is_user_in_queue(location_id, user_id):
    to_find: QueueModel = QueueModel(location_id=location_id, user_id=user_id)
    if (location_queue_list.get(location_id) is not None and isQueueModelInList(location_queue_list.get(location_id), to_find)):
        return True
    return False


def isQueueModelInList(location_list, queueModel):
    for qm in location_list:
        if (qm.location_id == queueModel.location_id and qm.user_id == queueModel.user_id):
            return True
        return False


def get_queue_size(location_id):
    if (location_queue_list.get(location_id) is not None):
        return len(location_queue_list.get(location_id))


def queue_number(location_id, user_id):
    to_find: QueueModel = QueueModel(location_id=location_id, user_id=user_id)
    if (location_queue_list.get(location_id) is not None and isQueueModelInList(location_queue_list.get(location_id), to_find)):
        return location_queue_list.get(location_id).index(to_find)
    return -1


def join_queue(location_id, user_id):
    qm: QueueModel = QueueModel(location_id=location_id, user_id=user_id)
    if (location_queue_list.get(location_id) is None):
        location_queue_list[location_id] = []
    location_queue_list[location_id].append(qm)
    LOGGER.info(location_queue_list)


def leave_queue(location_id, user_id):
    try:
        to_remove: QueueModel = QueueModel(
            location_id=location_id, user_id=user_id)
        if (location_queue_list.get(location_id) is not None and isQueueModelInList(location_queue_list.get(location_id), to_remove)):
            location_queue_list[location_id].remove(to_remove)

    # remove from skipped queue
        if (location_queue_skipped_list.get(location_id) is not None and isQueueModelInList(location_queue_skipped_list.get(location_id), to_remove)):
            location_queue_skipped_list[location_id].remove(to_remove)
        cancelTask(location_id)
    except ValueError as e:
        raise (e)


def skip_queue(location_id, user_id):
    try:
        if (location_queue_list.get(location_id) is not None):
            if (location_queue_skipped_list.get(location_id) is None):
                location_queue_skipped_list[location_id] = []
            location_queue_skipped_list[location_id].append(
                QueueModel(location_id=location_id, user_id=user_id))
            location_queue_list[location_id].remove(
                QueueModel(location_id=location_id, user_id=user_id))
        cancelTask(location_id)
    except ValueError as e:
        raise (e)


def cancelTask(location_id):
    if (location_task_list.get(location_id) is not None and location_task_list[location_id] is not None):

        location_task_list[location_id].cancel()
        # start_queue_operations(location_id=location_id)


def rearrange_queue(location_id):
    try:
        if (location_queue_list.get(location_id) is not None and len(location_queue_list.get(location_id)) > 0):
            location_queue_list.get(location_id).pop()
        if (location_queue_skipped_list.get(location_id) is not None):
            for q in location_queue_skipped_list[location_id]:
                qm: QueueModel = q
                location_queue_list[location_id].insert(0, qm)
            location_queue_skipped_list[location_id].clear()
    except ValueError as e:
        raise (e)


def check_if_queue_is_present(location_id):
    LOGGER.info(len(location_queue_list.get(location_id)))
    LOGGER.info(location_queue_list)
    return len(location_queue_list.get(location_id)) > 0


def get_first_user_in_queue(location_id):
    try:
        if (len(location_queue_list[location_id]) > 0):
            return location_queue_list[location_id][0].user_id
        return -1
    except ValueError as e:
        raise (e)


async def send_notification_to_join_queue(user_id, location_id, charger_id, connector_id):
    await fcm.send_notification(
        title="Your turn", body=f"It's your turn to charge now! on charger_id {charger_id} and connector number {connector_id}", user_id=user_id, data={'location_id': location_id, 'charger_id': charger_id, 'connector_id': connector_id}
    )


def start_queue_operations(location_id, charger_id, connector_id):
    try:
        user_id = get_first_user_in_queue(location_id=location_id)
        LOGGER.info("user id found is " + user_id)
        if (user_id != -1):
            location_task = asyncio.create_task(
                wait_for_user_to_respond(location_id, user_id, charger_id, connector_id))
            location_task_list[location_id] = location_task
            location_task.add_done_callback(remove_user_from_queue)
    except Exception as e:
        raise (e)


async def wait_for_user_to_respond(location_id, user_id, charger_id, connector_id):
    expiry_date = datetime.now() + timedelta(minutes=5)
    # (success, msg) = await ocpp_server.reserve_now(user_id=user_id, charger_id=charger_id, connector_id=connector_id, expiry_date=expiry_date)
    if (True):
        asyncio.create_task(send_notification_to_join_queue(
            user_id=user_id, location_id=location_id, charger_id=charger_id, connector_id=connector_id))
        await asyncio.sleep(300)
    return location_id, user_id, charger_id, connector_id


def remove_user_from_queue(task):
    try:
        res = task.result()
        leave_queue(res[0], res[1])
        start_queue_operations(
            location_id=res[0], charger_id=res[2], connector_id=res[3])
    except asyncio.CancelledError as e:
        print(e)
