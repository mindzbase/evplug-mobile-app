from errors.mysql_error import MissingObjectOnDB
from webapp_routes.dao import (
    add_generic_vehicle,
    get_generic_vehicle,
    link_generic_vehicle_with_user,
    verify_webapp_user,
)


async def verify_user_id(user_id):
    try:
        result = await verify_webapp_user(user_id)
        if not result:
            raise MissingObjectOnDB("User")
    except Exception as e:
        raise e


async def get_or_insert_vehicle():
    vehicle_id = await get_generic_vehicle()
    if not vehicle_id:
        vehicle_id = await add_generic_vehicle()
    return vehicle_id


async def set_vehicle(user_id):
    try:
        vehicle_id = await get_or_insert_vehicle()
        if not vehicle_id:
            raise MissingObjectOnDB("cannot get/add generic vehicle")
        await link_generic_vehicle_with_user(vehicle_id, user_id)
        return {"msg": "Vehicle linked successfully"}
    except MissingObjectOnDB as e:
        raise e
