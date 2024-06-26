from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict
import stripe
from aiohttp import web

import fcm
import razorpay
import mail
import ocpp_server
from service_layers.rfid_layer import get_rfid_of_user
import utils
from config import config
from constants import sort_order
from dao import app_dao, user_dao
from enums.span import Span
from errors.mysql_error import (
    ParameterMissing,
    PaymentMethodInvalid,
    check_empty_info,
)
from service_layers.app_layer import get_tenant_ids_based_on_mobile_app
from service_layers.idle_fee import get_idle_details
from smart_queue import (
    get_queue_size,
    is_user_in_queue,
    join_queue,
    leave_queue,
    queue_number,
    skip_queue,
)
from utils import generate_unique_key, validate_parameters


LOGGER = logging.getLogger("server")
user_routes = web.RouteTableDef()


@user_routes.get("/user/")
async def get_user_details(request: web.Request) -> web.Response:
    try:
        tenant_id = request["tenant_id"]
        user_id = request["user"]
        if user_id is None or tenant_id is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        business_mobile_app = request["business_mobile_app"]
        user_details_dict = await user_dao.get_user_details_with_user_id(
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )

        return web.Response(
            status=200,
            body=json.dumps(user_details_dict),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/notification")
async def get_user_notification(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        if user_id is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        await fcm.send_notification(
            title="Charging",
            body="Charging started Successfully",
            user_id=user_id,
            tenant_id=tenant_id
        )

        return web.Response(
            status=200,
            body=json.dumps({"test": "done"}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/get_wallet_balance")
async def get_wallet_balance(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        if user_id is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        user_details_dict = await user_dao.get_wallet_balance(
            user_id,
            tenant_id,
            business_mobile_app
        )
        balance = float(user_details_dict.get("wallet_balance"))
        user_details_dict["wallet_balance"] = f"{balance:.2f}"
        return web.Response(
            status=200,
            body=json.dumps(user_details_dict),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/add_wallet_balance")
async def add_wallet_balance(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        data: dict[str, Any] = await request.json()
        tenant_id = request["tenant_id"]
        if user_id is None or data.get("amount_added") is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        amount_added = data["amount_added"]
        business_mobile_app = request["business_mobile_app"]
        user_details_dict = await user_dao.get_wallet_balance(
            user_id,
            tenant_id,
            business_mobile_app
        )

        current_balance = user_details_dict["wallet_balance"]
        new_balance = float(amount_added) + float(current_balance)

        await user_dao.update_wallet_balance(
            new_balance=new_balance,
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app
        )

        return web.Response(
            status=200,
            body=json.dumps({"msg": "Wallet balance successfully added!"}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# TODO: discuss with sir. (about favourite station table)
@user_routes.get("/user/add_favorite_stations/")
async def add_favorite_stations(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        location_id = request.query["location_id"]
        tenant_id = request["tenant_id"]
        if (user_id is None) or (location_id is None):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        await user_dao.add_favorite_stations(user_id, location_id, tenant_id)
        return web.Response(
            status=200,
            body=json.dumps(
                {"msg": f"Station: {location_id!s} added for User: {user_id!s}"},
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# not in use
@user_routes.get("/user/get_favorite_stations/{day}")
async def get_favorite_stations(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        day = request.match_info["day"]
        tenant_id = request["tenant_id"]
        if (user_id is None) or (day is None):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        business_mobile_app = request["business_mobile_app"]
        stations = await user_dao.get_favorite_stations(
            user_id,
            day,
            tenant_id,
            business_mobile_app
        )
        org_ids_list = []
        for i in stations.values():
            org_ids_list.append(i.get("org_id"))
        org_ids = "', '".join(org_ids_list) if org_ids_list else "0"
        orgs_price_includes_tax = await user_dao.get_organisations_property(
            org_ids=org_ids, parameter_key="price_include_tax"
        )
        locations_ids = []
        for location in stations.keys():
            locations_ids.append(location)
        if not locations_ids:
            return web.Response(
                status=200,
                body=json.dumps({"charging_stations": []}),
                content_type="application/json",
            )
        private_charger_list = (
            await user_dao.check_and_get_if_user_authorize_on_charger(user_id=user_id)
        )
        authorized_charger_list = [
            charger.get("charger_id") for charger in private_charger_list
        ]
        chargers = await app_dao.get_all_charging_stations(
            locations_ids=locations_ids, authorized_charger_list=authorized_charger_list
        )
        for charging_station in chargers:
            chargers[charging_station]["connectors"].sort(
                key=lambda x: sort_order.index(x["status"])
            )
            price = chargers[charging_station].pop("price")
            bill_by = chargers[charging_station].pop("bill_by")
            loc_org_id = chargers[charging_station].pop("org_id")
            for connector in chargers[charging_station]["connectors"]:
                connector["price"] = price
                connector["bill_by"] = bill_by
                connector["plan_type"] = "public"
                connector["price_include_tax"] = bool(
                    int(orgs_price_includes_tax.get(loc_org_id, 0))
                )
        for charging_station in chargers.values():
            location_id = charging_station["location_id"]
            if stations[location_id].get("chargers"):
                stations[location_id]["chargers"].append(charging_station)
            else:
                stations[location_id]["chargers"] = []
                stations[location_id]["chargers"].append(charging_station)
        amenities = await app_dao.get_location_amenities(locations_ids)
        for amenity in amenities:
            location_id = amenity
            stations[location_id]["amenities"] = amenities[amenity]
        images = await app_dao.get_location_images(locations_ids)

        for image in images:
            location_id = image
            stations[location_id]["images"] = images[image]

        stations_list = []
        for station in stations.values():
            stations_list.append(station)
        return web.Response(
            status=200,
            body=json.dumps({"charging_stations": stations_list}),
            content_type="application/json",
        )

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# TODO: discuss with sir. (about favourite station table)
@user_routes.get("/user/remove_favorite_stations/")
async def remove_favorite_stations(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        location_id = request.query["location_id"]
        if (user_id is None) or (location_id is None):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        tenant_id = request["tenant_id"]
        await user_dao.remove_favorite_stations(user_id, location_id, tenant_id)
        return web.Response(
            status=200,
            body=json.dumps(
                {"msg": f"Station: {location_id!s} removed for User: {user_id!s}"},
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/add_vehicle/{vehicle_id}")
async def add_users_vehicle(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        vehicle_id = request.match_info["vehicle_id"]
        if (user_id is None) or (vehicle_id is None):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        id = await user_dao.add_users_vehicle(
            user_id,
            vehicle_id,
            tenant_id,
            business_mobile_app
        )
        await user_dao.set_default_vehicle(
            user_id=user_id,
            vehicle_id=vehicle_id,
            business_mobile_app=business_mobile_app,
            tenant_id=tenant_id
        )

        return web.Response(
            status=200,
            body=json.dumps(
                {
                    "msg": f"""
                        Vehicle {vehicle_id} added for User {user_id}
                        with unique_id: {id}
                    """
                }
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/remove_vehicle/{vehicle_id}")
async def remove_users_vehicle(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        vehicle_id = request.match_info["vehicle_id"]
        if (user_id is None) or (vehicle_id is None):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        res = await user_dao.check_user_vehicle_exist(
            vehicle_id=vehicle_id,
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app
        )
        if res is None:
            return web.Response(
                status=400,
                body=json.dumps(
                    {"msg": f"No user vehicle exist with {vehicle_id}"}),
                content_type="application/json",
            )
        await user_dao.remove_users_vehicle(
            vehicle_id=vehicle_id,
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app
        )
        return web.Response(
            status=200,
            body=json.dumps(
                {"msg": f"user_vehicle removed with unique_id: {vehicle_id}"}
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/get/connector_status/")
async def get_connector_status(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        charger_id = request.query["charger_id"]
        connector_id = request.query["connector_id"]
        tenant_id = request["tenant_id"]
        if (user_id is None) or (connector_id is None) or (charger_id is None):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        connector_status = await user_dao.get_specified_connector_status(
            charger_id, connector_id, tenant_id
        )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "Success", "status": connector_status}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/app/start_charging")
async def start_charging(request: web.Request) -> web.Response:
    try:
        data: Dict[str, Any] = await request.json()
        user_id = request["user"]
        charger_id = data.get("charger_id", None)
        connector_id = data.get("connector_id", None)
        if (charger_id is None) or (connector_id is None):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        tenant_id = request["tenant_id"]
        id_tag = await user_dao.get_users_id_tag(user_id, tenant_id)
        existing_session = await user_dao.get_current_running_session_id_with_id_tag(
            id_tag=id_tag, tenant_id=tenant_id
        )
        if existing_session:
            is_session_started = False
            msg = f"""
                User have Existing session running with session_id {existing_session}.
            """
        else:
            is_session_started, msg = await ocpp_server.remote_start(
                charger_id=charger_id,
                id_tag=id_tag,
                connector_id=connector_id,
                tenant_id=tenant_id,
            )

        if is_session_started:
            session_id, start_time = await user_dao.get_current_running_session_id(
                charger_id=charger_id,
                connector_id=connector_id,
                id_tag=id_tag,
                tenant_id=tenant_id
            )

            return web.Response(
                status=200,
                body=json.dumps(
                    {"msg": "Charging started Successfully",
                        "session_id": session_id}
                ),
                content_type="application/json",
            )
        await fcm.send_notification(
            title="Oops!",
            body=f"Charger {charger_id} refused to start charging!",
            user_id=user_id,
        )
        return web.Response(
            status=400,
            body=json.dumps(
                {
                    "msg": f"{msg}",
                }
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/start_charging")
async def start_charging_v2(request: web.Request) -> web.Response:
    try:
        business_mobile_app = request['business_mobile_app']
        data: Dict[str, Any] = await request.json()
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        charger_id = data.get("charger_id", None)
        connector_id = data.get("connector_id", None)
        if (charger_id is None) or (connector_id is None):
            return web.Response(
                status=400,
                body=json.dumps(
                    {"msg": "Invalid Parameters", "status": "unauthorized"}
                ),
                content_type="application/json",
            )
        # should_start_charging = True
        id_tag = await user_dao.get_users_id_tag(user_id, tenant_id, business_mobile_app)
        charger_details = await user_dao.charger_detail(
            charger_id=charger_id,
            tenant_id=tenant_id,
        )
        # if not (bool(charger_details.get("public", 1))):
        #     charger_group = await user_dao.check_and_get_if_user_authorize_on_charger(
        #         charger_id=charger_id, user_id=user_id
        #     )
        #     should_start_charging = True if charger_group else False

        # if not should_start_charging:
        #     return web.Response(
        #         status=200,
        #         body=json.dumps(
        #             {"msg": "User is not authorized", "status": "unauthorized"}
        #         ),
        #         content_type="application/json",
        #     )
        is_session_started, msg = await ocpp_server.remote_start(
            charger_id=charger_id,
            id_tag=id_tag,
            connector_id=connector_id,
            tenant_id=tenant_id
        )

        if is_session_started:
            await fcm.send_notification(
                title="Session Started",
                body=f"Charging started successfully on charger ${charger_id}",
                user_id=user_id,
                tenant_id=tenant_id
            )
            return web.Response(
                status=200,
                content_type="application/json",
                body=json.dumps(
                    {"msg": "Charging started Successfully", "status": "authorized"}
                ),
            )
        await fcm.send_notification(
            title="Oops!",
            body=f"Charger {charger_id} refused to start charging!",
            user_id=user_id,
            tenant_id=tenant_id
        )
        return web.Response(
            status=400,
            body=json.dumps({"msg": f"{msg}", "status": "unauthorized"}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/stop_public_charging")
async def stop_public_charging(request: web.Request) -> web.Response:
    try:
        data: Dict[str, Any] = await request.json()
        user_id = request["user"]
        session_id = data["session_id"]
        if session_id is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        id_tag = await user_dao.get_users_id_tag(
            user_id, tenant_id, business_mobile_app)
        (is_stopped, msg) = await ocpp_server.remote_stop(session_id, id_tag, tenant_id)
        LOGGER.info(f"is_stopped: {is_stopped}")
        LOGGER.info(f"msg: {msg}")
        res = {"is_stopped": is_stopped, "msg": msg}
        if res["is_stopped"]:
            await fcm.send_notification(
                title="Success",
                body="Charging stopped successfully",
                user_id=user_id,
                tenant_id=tenant_id,
            )
            return web.Response(
                status=200,
                body=json.dumps(res),
                content_type="application/json",
            )
        await fcm.send_notification(
            title="Oops",
            body="Unable to stop charging session",
            user_id=user_id,
            tenant_id=tenant_id,
        )
        return web.Response(
            status=400,
            body=json.dumps(
                {
                    "msg": f"""
                        Unable to stop charging session. Please Try again!.
                        Error {res['msg']}
                    """
                }
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/charger_info/{charger_id}/{day}")
async def get_charger_info(request: web.Request) -> web.Response:
    try:
        # request["user"]
        charger_id = request.match_info["charger_id"]
        day = request.match_info["day"]
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        validate_parameters(charger_id, day, tenant_id, user_id)
        location_id = await user_dao.charger_location_id(charger_id, tenant_id)
        res = await user_dao.get_charger_details_with_id(
            location_id=location_id,
            day=day,
            tenant_id=tenant_id,
            charger_id=charger_id,
        )

        return web.Response(
            status=200, body=json.dumps(res), content_type="application/json"
        )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# TODO: ask sir if home charging apis needed or not
# @user_routes.get("/user/charging_session_history/")
# async def get_charging_session_history(request: web.Request) -> web.Response:
#     try:
#         user_id = request["user"]
#         tenant_id = request["tenant_id"]
#         validate_parameters(user_id, tenant_id)
#         res_list = await user_dao.get_charging_session_history(user_id, tenant_id)
#         return web.Response(
#             status=200,
#             body=json.dumps({"session_history": res_list}),
#             content_type="application/json",
#         )
#     except ParameterMissing as e:
#         return e.jsonResponse
#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


@user_routes.get("/user/connector_status/")
async def connector_status(request: web.Request) -> web.Response:
    try:
        request["user"]
        charger_id = request.query["charger_id"]
        connector_id = request.query["connector_id"]
        tenant_id = request["tenant_id"]
        validate_parameters(charger_id, connector_id, tenant_id)
        connector_status = await user_dao.get_specified_connector_status(
            charger_id, connector_id, tenant_id
        )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "Success", "status": connector_status}),
            content_type="application/json",
        )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# @user_routes.get("/user/meter_values/")
# async def get_meter_values(request: web.Request) -> web.Response:
#     try:
#         session_id = request.query["session_id"]
#         user_id = request["user"]
#         tenant_id = request["tenant_id"]
#         validate_parameters(session_id, user_id, tenant_id)
#         # session can be started with id tag admin
#         is_running, start_time = await user_dao.is_session_running(
#             session_id=session_id, tenant_id=tenant_id
#         )
#         if not is_running:
#             return web.Response(
#                 status=400,
#                 body=json.dumps({"msg": "No session running on charger!"}),
#                 content_type="application/json",
#             )
#         (
#             initial_meter_value,
#             energy_import_register,
#             energy_import_unit,
#             power_import_register,
#             power_import_unit,
#             soc,
#             charger_id,
#         ) = await user_dao.get_session_meter_values(
#             session_id=session_id,
#             tenant_id=tenant_id
#         )

#         current_time = datetime.utcnow()
#         duration = current_time - start_time
#         hours = duration.total_seconds() / 3600

#         if energy_import_unit == "Wh":
#             energy_import_register /= 1000
#         if power_import_unit == "W":
#             power_import_register /= 1000
#         initial_meter_value /= 1000

#         current_session_energy = round(energy_import_register - initial_meter_value, 2)
#         res = await user_dao.get_session_duration_and_charger_details(
#             session_id=session_id
#         )

#         if not res:
#             raise MissingInfoException("session duration or price plan is missing")

#         (
#             stop_charging_by,
#             bill_by,
#             price,
#             end_time,
#             paid_amount,
#         ) = res

#         if stop_charging_by == "end_time":
#             spent_duration = current_time - start_time
#             total_duration = end_time - start_time
#             percent = (
#                 1 / total_duration.total_seconds()
#             ) * spent_duration.total_seconds()

#             hours, remainder = divmod(spent_duration.total_seconds(), 3600)
#             minutes, seconds = divmod(remainder, 60)
#             spent_duration_string = "{:02} hr:{:02} min".format(
#                 int(hours), int(minutes)
#             )
#             data = {
#                 "power": str(power_import_register),
#                 "energy_transfer": str(current_session_energy),
#                 "soc": str(soc),
#                 "end_time": str(end_time),
#                 "duration": spent_duration_string,
#                 "duration_percentage": percent,
#             }
#             await send_message_to_client(
#                 key=user_id, event_name="meter_values", data=data
#             )
#             return web.Response(
#                 status=200,
#                 body=json.dumps(data),
#                 content_type="application/json",
#             )
#         else:
#             organisation_properties = await user_dao.get_organisation_properties(
#                 org_id=org_id
#             )
#             price_include_tax = bool(
#                 int(organisation_properties.get("price_include_tax", 0))
#             )
#             tax = float(organisation_properties.get("tax_percentage", 5))
#             entity = hours if bill_by == "per_hour" else current_session_energy
#             if price_include_tax:
#                 cost_with_tax = entity * price
#                 cost, tax = utils.calculate_base_and_tax(
#                     total_amount=cost_with_tax, tax_percentage=tax
#                 )
#             else:
#                 cost = entity * price
#                 tax, cost_with_tax = utils.calculate_tax_and_total(
#                     base_amount=cost, tax_percentage=tax
#                 )
#             data = {
#                 "power": str(power_import_register),
#                 "energy_transfer": str(current_session_energy),
#                 "soc": str(soc),
#                 "paid_amount": paid_amount,
#                 "cost": cost,
#                 "cost_with_tax": cost_with_tax,
#             }
#             await send_message_to_client(
#                 key=user_id, event_name="meter_values", data=data
#             )
#             return web.Response(
#                 status=200,
#                 body=json.dumps(data),
#                 content_type="application/json",
#             )
#     except ParameterMissing as e:
#         return e.jsonResponse
#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


@user_routes.get("/user/statistics/")
async def statistics(request: web.Request) -> web.Response:
    try:
        charger_id = request.query["charger_id"]
        from_time = request.query["from_time"]
        to_time = request.query["to_time"]
        span = Span[request.query["span"]]
        if charger_id is None and (not charger_id == ""):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        request["user"]
        statistics = await user_dao.get_charging_statistics(
            charger_id=charger_id, from_time=from_time, to_time=to_time, span=span
        )

        # "energy_list": [
        #     {
        #         "time": "39",
        #         "energy_start": "0.1",
        #         "energy_stop": "0.2"
        #     },
        #     {
        #         "time": "40",
        #         "energy_start": "0",
        #         "energy_stop": "71"
        #     },
        #     {
        #         "time": "41",
        #         "energy_start": "0",
        #         "energy_stop": "25"
        #     }
        # ]
        if span == Span.day:
            new_energy_list = []
            dict_12_359 = {
                "time": "12AM-3:59AM",
                "energy_start": 0.0,
                "energy_stop": 0.0,
            }
            dict_4_759 = {"time": "4AM-7:59AM",
                          "energy_start": 0.0, "energy_stop": 0.0}
            dict_8_1159 = {
                "time": "8AM-11:59AM",
                "energy_start": 0.0,
                "energy_stop": 0.0,
            }
            dict_12_359pm = {
                "time": "12PM-3:59PM",
                "energy_start": 0.0,
                "energy_stop": 0.0,
            }
            dict_4_8pm = {"time": "4PM-7:59PM",
                          "energy_start": 0.0, "energy_stop": 0.0}
            dict_8_1159pm = {
                "time": "8PM-11:59PM",
                "energy_start": 0.0,
                "energy_stop": 0.0,
            }
            for energy in statistics["energy_list"]:
                if int(energy["time"]) >= 0 and int(energy["time"]) < 4:
                    dict_12_359["energy_start"] += float(
                        energy["energy_start"])
                    dict_12_359["energy_stop"] += float(energy["energy_stop"])
                elif int(energy["time"]) >= 4 and int(energy["time"]) < 8:
                    dict_4_759["energy_start"] += float(energy["energy_start"])
                    dict_4_759["energy_stop"] += float(energy["energy_stop"])
                elif int(energy["time"]) >= 8 and int(energy["time"]) < 12:
                    dict_8_1159["energy_start"] += float(
                        energy["energy_start"])
                    dict_8_1159["energy_stop"] += float(energy["energy_stop"])
                elif int(energy["time"]) >= 12 and int(energy["time"]) < 16:
                    dict_12_359pm["energy_start"] += float(
                        energy["energy_start"])
                    dict_12_359pm["energy_stop"] += float(
                        energy["energy_stop"])
                elif int(energy["time"]) >= 16 and int(energy["time"]) < 20:
                    dict_4_8pm["energy_start"] += float(energy["energy_start"])
                    dict_4_8pm["energy_stop"] += float(energy["energy_stop"])
                elif int(energy["time"]) >= 20 and int(energy["time"]) < 24:
                    dict_8_1159pm["energy_start"] += float(
                        energy["energy_start"])
                    dict_8_1159pm["energy_stop"] += float(
                        energy["energy_stop"])

            dict_12_359["energy_start"] = str(dict_12_359["energy_start"])
            dict_12_359["energy_stop"] = str(dict_12_359["energy_stop"])

            dict_4_759["energy_start"] = str(dict_4_759["energy_start"])
            dict_4_759["energy_stop"] = str(dict_4_759["energy_stop"])

            dict_8_1159["energy_start"] = str(dict_8_1159["energy_start"])
            dict_8_1159["energy_stop"] = str(dict_8_1159["energy_stop"])

            dict_12_359pm["energy_start"] = str(dict_12_359pm["energy_start"])
            dict_12_359pm["energy_stop"] = str(dict_12_359pm["energy_stop"])

            dict_4_8pm["energy_start"] = str(dict_4_8pm["energy_start"])
            dict_4_8pm["energy_stop"] = str(dict_4_8pm["energy_stop"])

            dict_8_1159pm["energy_start"] = str(dict_8_1159pm["energy_start"])
            dict_8_1159pm["energy_stop"] = str(dict_8_1159pm["energy_stop"])

            dict_12_359["energy_start"] = str(dict_12_359["energy_start"])
            dict_12_359["energy_stop"] = str(dict_12_359["energy_stop"])
            new_energy_list.append(dict_12_359)
            new_energy_list.append(dict_4_759)
            new_energy_list.append(dict_8_1159)
            new_energy_list.append(dict_12_359pm)
            new_energy_list.append(dict_4_8pm)
            new_energy_list.append(dict_8_1159pm)

            statistics["energy_list"] = new_energy_list

        return web.Response(
            status=200,
            body=json.dumps(
                {"msg": "Success", "statistics": statistics, "span": span}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/change_password")
async def change_password(request: web.Request) -> web.Response:
    try:
        data: Dict[str, Any] = await request.json()
        if data.get("old_password") is None or data.get("new_password") is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        user_id = request["user"]
        old_password = data["old_password"]
        new_password = data["new_password"]
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        current_pass = await user_dao.get_user_password(
            user_id, tenant_id, business_mobile_app
        )
        if current_pass is None or not (
            utils.check_password(old_password, current_pass)
        ):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Current Password"}),
                content_type="application/json",
            )
        await user_dao.update_user_password(
            user_id, utils.encrypt_password(new_password),
            tenant_id, business_mobile_app
        )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "Password Updated Successfully!"}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# @user_routes.post("/user/stop_charging_cloudwatch")
# async def stop_charging_cloudwatch(request: web.Request) -> web.Response:
#     try:
#         data: Dict[str, Any] = await request.json()
#         if (
#             data.get("charger_id") is None
#             or data.get("start_id") is None
#             or data.get("stop_id") is None
#         ):
#             return web.Response(
#                 status=400,
#                 body=json.dumps({"msg": "Invalid Parameters"}),
#                 content_type="application/json",
#             )
#         request["user"]
#         start_id = data["start_id"]
#         stop_id = data["stop_id"]
#         charger_id = data["charger_id"]
#         await user_dao.update_stop_schedule_id(start_id, stop_id, charger_id)
#         return web.Response(
#             status=200,
#             body=json.dumps({"msg": "Token added Successfully!"}),
#             content_type="application/json",
#         )
#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


# @user_routes.get("/user/estimates/")
# async def get_charging_estimates(request: web.Request) -> web.Response:
#     try:
#         request["user"]
#         charger_id = request.query["charger_id"]
#         connector_id = request.query["connector_id"]
#         vehicle_id = request.query["vehicle_id"]
#         duration_string = request.query.get("duration", None)
#         paid_amount = request.query.get("amount", None)
#         if (
#             charger_id is None
#             or charger_id == ""
#             or connector_id is None
#             or vehicle_id is None
#         ):
#             return web.Response(
#                 status=400,
#                 body=json.dumps({"msg": "Invalid Parameters"}),
#                 content_type="application/json",
#             )
#         if duration_string is None and paid_amount is None and duration_string == "":
#             return web.Response(
#                 status=400,
#                 body=json.dumps({"msg": "Invalid Parameters"}),
#                 content_type="application/json",
#             )
#         connector_details = await user_dao.get_connector_details(
#             charger_id, connector_id
#         )
#         vehicle_details = await user_dao.get_vehicle_details(vehicle_id)
#         if connector_details is None or vehicle_details is None:
#             return web.Response(
#                 status=400,
#                 body=json.dumps({"msg": "Invalid Parameters"}),
#                 content_type="application/json",
#             )
#         bill_by = connector_details["bill_by"]
#         tax = 5
#         if bill_by == "per_hour":
#             if duration_string:
#                 duration = duration_string.split(":")
#                 duration_in_minutes = int(duration[0]) * 60
#                 amount = By_hour.duration.get_amount(
#                     duration_in_minutes, connector_details["price"]
#                 )
#                 total_amount, tax_amount = utils.calculate_tax_amount(amount, tax)
#                 units_consumed = By_hour.duration.get_units_consumed(
#                     duration_in_minutes, connector_details["max_output"]
#                 )
#                 soc_added = utils.get_soc_added(
#                     vehicle_details["battery_size"], units_consumed
#                 )
#                 range_added = utils.get_range_added(vehicle_details["range"], soc_added)
#                 response = {
#                     "amount": round(amount, 2),
#                     "tax_amount": round(tax_amount, 2),
#                     "total_amount": round(total_amount, 2),
#                     "units": round(units_consumed, 2),
#                     "soc_added": round(soc_added, 0),
#                     "range_added": round(range_added, 2),
#                 }
#             if paid_amount:
#                 paid_amount = float(paid_amount)
#                 total_amount, tax_amount = utils.calculate_tax_amount(paid_amount, tax)
#                 units, duration = By_hour.amount.get_units_consumed(
#                     paid_amount,
#                     connector_details["max_output"],
#                     connector_details["price"],
#                 )
#                 soc_added = utils.get_soc_added(vehicle_details["battery_size"], units)
#                 range_added = utils.get_range_added(vehicle_details["range"], soc_added)
#                 response = {
#                     "amount": round(paid_amount, 2),
#                     "tax_amount": round(tax_amount, 2),
#                     "total_amount": round(total_amount, 2),
#                     "units": round(units, 2),
#                     "expected_time": round(duration, 0),
#                     "soc_added": round(soc_added, 0),
#                     "range_added": round(range_added, 2),
#                 }
#         if bill_by == "per_unit":
#             if paid_amount:
#                 paid_amount = float(paid_amount)
#                 total_amount, tax_amount = utils.calculate_tax_amount(paid_amount, tax)
#                 units, duration = By_unit.amount.get_units_consumed(
#                     paid_amount,
#                     connector_details["max_output"],
#                     connector_details["price"],
#                 )
#                 soc_added = utils.get_soc_added(vehicle_details["battery_size"], units)
#                 range_added = utils.get_range_added(vehicle_details["range"], soc_added)
#                 response = {
#                     "amount": round(paid_amount, 2),
#                     "tax_amount": round(tax_amount, 2),
#                     "total_amount": round(total_amount, 2),
#                     "units": round(units, 2),
#                     "expected_time": round(duration, 0),
#                     "soc_added": round(soc_added, 0),
#                     "range_added": round(range_added, 2),
#                 }

#         return web.Response(
#             status=200, body=json.dumps(response), content_type="application/json"
#         )
#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


# @user_routes.post("/user/get_running_sessions/")
# async def get_running_sessions(request: web.Request) -> web.Response:
#     try:
#         request["user"]
#         data: Dict[str, Any] = await request.json()
#         session_list = data.get("session_ids")
#         session_ids = ""
#         session_ids = ",".join([str(x) for x in session_list])
#         if len(session_list):
#             session_details = await user_dao.get_running_session_details(session_ids)
#             return web.Response(
#                 status=200,
#                 body=json.dumps(session_details),
#                 content_type="application/json",
#             )

#         return web.Response(
#             status=200,
#             body=json.dumps({"msg": "No session running on charger and connector"}),
#             content_type="application/json",
#         )
#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


@user_routes.get("/user/get_running_sessions_v2/")
async def get_running_sessions_v2(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        tenant_id_list = await get_tenant_ids_based_on_mobile_app(
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )

        tasks1 = []
        session_ids = {}

        for tenant_id in tenant_id_list:
            tasks1.append(user_dao.get_current_running_sessions_in_organisations(
                tenant_id=tenant_id,
            ))
            session_ids[tenant_id] = []
        results = await asyncio.gather(*tasks1)

        sessions_list = []
        for result in results:
            sessions_list += result

        tenant_id_cards = await get_rfid_of_user(
            business_mobile_app, user_id, tenant_id_list
        )

        for session in sessions_list:
            if session["id_tag"] in tenant_id_cards[session["tenant_id"]]:
                session_ids[session["tenant_id"]].append(session["id"])

        tasks2 = []
        for tenant, session_list in session_ids.items():
            if len(session_list):
                session_ids_string = ",".join([str(x) for x in session_list])
                tasks2.append(user_dao.get_running_session_details_v2(
                    session_ids_string, tenant, business_mobile_app
                ))

        session_details = []
        if tasks2:
            multiple_session_details = await asyncio.gather(*tasks2)
            for session in multiple_session_details:
                session_details += session

            def get_datetime(item):
                if "startTime" in item:
                    start_time = item.pop("startTime")
                    return start_time
                else:
                    return None

            sorted_result = sorted(
                session_details, key=lambda x: get_datetime(x), reverse=True)
            return web.Response(
                status=200,
                body=json.dumps({"sessions": sorted_result}),
                content_type="application/json",
            )

        return web.Response(
            status=200,
            body=json.dumps({"sessions": []}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# @user_routes.post("/user/update_user")
# async def add_user_details(request: web.Request) -> web.Response:
#     try:
#         data: Dict[str, Any] = await request.json()
#         user_id = request["user"]
#         if (
#             data.get("name") is None
#             or data.get("email") is None
#             or data.get("gender") is None
#             or data.get("dob") is None
#             or user_id is None
#         ):
#             return web.Response(
#                 status=400,
#                 body=json.dumps({"msg": "Invalid Parameters"}),
#                 content_type="application/json",
#             )
#         name = data["name"]
#         email = data["email"]
#         gender = data["gender"]
#         dob = data["dob"]
#         await user_dao.update_user(
#             user_id=user_id, name=name, email=email, gender=gender, dob=dob
#         )
#         return web.Response(
#             status=200,
#             body=json.dumps(
#                 {"msg": "User added Successfully!", "user_id": str(user_id)}
#             ),
#             content_type="application/json",
#         )
#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


@user_routes.post("/user/update_userv2")
async def update_userv2(request: web.Request) -> web.Response:
    try:
        data: Dict[str, Any] = await request.json()
        user_id = request["user"]
        name = data.get("name")
        email = data.get("email")
        token = data.get("token")
        address = data.get("address")
        os = data.get("os")
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        await user_dao.update_userv2(
            user_id=user_id,
            name=name,
            email=email,
            token=token,
            address=address,
            os=os,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )
        return web.Response(
            status=200,
            body=json.dumps(
                {"msg": "User updated Successfully!", "user_id": str(user_id)}
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/charging_history/")
async def charging_history(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        validate_parameters(user_id, tenant_id)
        business_mobile_app = request["business_mobile_app"]
        res = await user_dao.get_charging_history(
            user_id, tenant_id, business_mobile_app
        )
        if res:
            return web.Response(
                status=200, body=json.dumps(res), content_type="application/json"
            )
        else:
            return web.Response(
                status=200,
                body=json.dumps(
                    {"msg": f"No charging History found for user {user_id}"}
                ),
                content_type="application/json",
            )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# TODO: confirm first it's useful or not
@user_routes.post("/user/create-setup-intent/")
async def create_setup_intent(request):
    try:
        user_id = request["user"]
        data: Dict[str, Any] = await request.json()
        if data.get("email") is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        email = data["email"]
        isProd = True if (request.headers.get(
            "isProd", "") == "true") else False
        stripe.api_key = (
            config["STRIPE_API_KEY"] if (
                isProd) else config["STRIPE_TEST_API_KEY"]
        )
        res = await user_dao.get_stripe_cust_id(user_id)
        cust_id = res.get("cust_id") if res else None
        if not cust_id:
            customer = stripe.Customer.create(email=email)
            cust_id = customer.id
            await user_dao.insert_stripe_customer(user_id, cust_id)

        customer = stripe.Customer.retrieve(cust_id)

        setup_intent = stripe.SetupIntent.create(
            payment_method_types=["card"], customer=customer
        )
        return web.Response(
            status=200,
            body=json.dumps(
                {
                    "client_secret": f"{setup_intent.get('client_secret', None)}",
                }
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# TODO: confirm first it's useful or not
@user_routes.get("/user/get_cards/")
async def get_cards(request):
    try:
        user_id = request["user"]
        isProd = True if (request.headers.get(
            "isProd", "") == "true") else False
        stripe.api_key = (
            config["STRIPE_API_KEY"] if (
                isProd) else config["STRIPE_TEST_API_KEY"]
        )
        res = await user_dao.get_stripe_cust_id(user_id)
        cust_id = res.get("cust_id") if res else None
        cards = []
        if not cust_id:
            return web.Response(
                status=200,
                body=json.dumps(cards),
                content_type="application/json",
            )

        customer = stripe.Customer.retrieve(cust_id)
        payment_methods = stripe.Customer.list_payment_methods(
            customer, type="card")
        logos = await user_dao.get_card_logos()
        if payment_methods:
            for i in payment_methods:
                card = {
                    "brand": i.card.brand,
                    "exp_month": i.card.exp_month,
                    "exp_year": i.card.exp_year,
                    "last_digits": i.card.last4,
                    "payment_method_id": i.id,
                    "logo_url": logos.get(i.card.brand)
                    if i.card.brand in logos.keys()
                    else "",
                }
                cards.append(card)
        return web.Response(
            status=200,
            body=json.dumps(cards),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# TODO: confirm first it's useful or not
@user_routes.post("/user/remove_card/")
async def remove_card(request):
    try:
        user_id = request["user"]
        data: Dict[str, Any] = await request.json()
        payment_method_id = data.get("payment_method_id", "")
        isProd = request.headers.get("isProd", "") == "true"
        stripe.api_key = (
            config["STRIPE_API_KEY"] if (
                isProd) else config["STRIPE_TEST_API_KEY"]
        )
        res = await user_dao.get_stripe_cust_id(user_id)
        cust_id = res.get("cust_id") if res else None
        payment_id_list = []
        if not cust_id:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "stripe user not found."}),
                content_type="application/json",
            )

        customer = stripe.Customer.retrieve(cust_id)

        payment_methods = stripe.Customer.list_payment_methods(
            customer, type="card")
        payment_id_list = payment_methods and [i.id for i in payment_methods]
        is_valid_payment_id = payment_method_id in payment_id_list
        if not is_valid_payment_id:
            return web.Response(
                status=400,
                body=json.dumps(
                    {"msg": "payment intent id is either invalid / not belong to user"}
                ),
                content_type="application/json",
            )

        stripe.PaymentMethod.detach(payment_method_id)
        return web.Response(
            status=200,
            body=json.dumps({"msg": "card is removed successfully."}),
            content_type="application/json",
        )

    except ParameterMissing as e:
        LOGGER.error(e)
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# TODO: confirm first it's useful or not
@user_routes.post("/user/capture_card/")
async def capture_card(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        request.headers["organisationId"]
        data: Dict[str, Any] = await request.json()
        payment_method_id = data.get("payment_method_id")
        currency = data.get("currency")
        amount = data.get("amount")
        capture_method = data.get("capture_method")
        isProd = True if (request.headers.get(
            "isProd", "") == "true") else False
        stripe.api_key = (
            config["STRIPE_API_KEY"] if (
                isProd) else config["STRIPE_TEST_API_KEY"]
        )
        if not payment_method_id:
            raise PaymentMethodInvalid()
        if not amount or not currency:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        res = await user_dao.get_stripe_cust_id(user_id)
        cust_id = res.get("cust_id") if res else None
        card_hold_intent = stripe.PaymentIntent.create(
            amount=int(float(amount) * 100),
            currency=currency,
            payment_method_types=["card"],
            capture_method="automatic" if not capture_method else capture_method,
            payment_method=payment_method_id,
            customer=cust_id,
            confirm=True,
            description="Authorization for EV charging",
            # shipping={
            #     "address": {
            #         "city": "Dubai",
            #         "country": "United Arab Emirates",
            #         "line1": "in5 design",
            #     },
            #     "name": "Aditya Bhaumik",
            # },
        )
        # stripe.PaymentIntent.confirm(card_hold_intent.id)
        if card_hold_intent.status == "succeeded":
            user_details_dict = await user_dao.get_wallet_balance(user_id)

            current_balance = user_details_dict["wallet_balance"]
            new_balance = float(amount) + float(current_balance)

            await user_dao.update_wallet_balance(
                new_balance=new_balance,
                user_id=user_id,
            )

            res = await user_dao.insert_stripe_payment_info(
                user_id=user_id, payment_id=card_hold_intent.id, amount=amount
            )

        return web.Response(
            status=200,
            body=json.dumps(
                {
                    "msg": "Your card mandate is created successfully",
                    "client_secret": f"{card_hold_intent.get('client_secret', None)}",
                    "payment_intent_id": str(card_hold_intent.id),
                    "status": card_hold_intent.status,
                }
            ),
            content_type="application/json",
        )

    except PaymentMethodInvalid as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {
                    "msg": f"""
                {e.message}.Please contact our team for further support.
            """
                }
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# TODO: confirm first it's useful or not
@user_routes.post("/user/save_captured_card/")
async def save_captured_card(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        data: Dict[str, Any] = await request.json()
        payment_intent_id = data.get("payment_intent_id")
        payment_method_id = data.get("payment_method_id")
        currency = data.get("currency")
        charger_id = data.get("charger_id")
        connector_id = data.get("connector_id")
        amount = data.get("amount")
        isProd = True if (request.headers.get(
            "isProd", "") == "true") else False
        stripe.api_key = (
            config["STRIPE_API_KEY"] if (
                isProd) else config["STRIPE_TEST_API_KEY"]
        )
        if not payment_method_id or not payment_intent_id:
            raise PaymentMethodInvalid()
        if not charger_id or not connector_id or not currency or not amount:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        res = await user_dao.get_stripe_cust_id(user_id)
        cust_id = res.get("cust_id") if res else None
        await user_dao.insert_payment_intent_info(
            payment_intent_id=payment_intent_id,
            payment_method_id=payment_method_id,
            charger_id=charger_id,
            connector_id=connector_id,
            user_id=user_id,
            amount=int(float(amount)),
            currency=currency,
            cust_id=cust_id,
        )
        return web.Response(
            status=200,
            body=json.dumps(
                {
                    "msg": "Mandate Details are saved successfully.",
                }
            ),
            content_type="application/json",
        )

    except PaymentMethodInvalid as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {
                    "msg": f"""
                {e.message}.Please contact our team for further support.
            """
                }
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# used on case of applepay
@user_routes.post("/user/payment_method_and_intent/")
async def payment_method_and_intent(request):
    try:
        request["user"]
        data: Dict[str, Any] = await request.json()
        if (
            data.get("email") is None
            or data.get("request_three_d_secure") is None
            or data.get("amount") is None
        ):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        user_email = data["email"]
        amount = data["amount"]
        # request_three_d_secure = data["request_three_d_secure"]
        currency = "aed"
        capture_method = data.get("capture_method")

        isProd = True if (request.headers.get(
            "isProd", "") == "true") else False
        stripe.api_key = (
            config["STRIPE_API_KEY"] if (
                isProd) else config["STRIPE_TEST_API_KEY"]
        )

        customer = stripe.Customer.list(email=user_email)
        if not customer.data:
            customer = stripe.Customer.create(email=user_email)

        # paymentMethods = stripe.Customer.list_payment_methods(
        #     customer.data[0]['id'],
        #     # type="card",
        # )

        ephemeralKey = stripe.EphemeralKey.create(
            customer=customer.data[0]["id"],
            stripe_version="2022-11-15",
        )
        payment_intent = stripe.PaymentIntent.create(
            customer=customer.data[0]["id"],
            amount=int(float(amount) * 100),
            currency=currency,
            description="Apple Pay payment for EV charging!",
            capture_method="automatic" if not capture_method else capture_method,
            automatic_payment_methods={
                "enabled": True,
            },
            shipping={
                "name": "Najhum Technologies LLC",
                "address": {"city": "dubai", "country": "AE"},
            },
        )

        # payment_intent = stripe.PaymentIntent.create(
        #     amount=amount,
        #     currency=currency,
        #     customer=customer.data[0]['id'],
        #     # payment_method_options={
        #     #     "card": {
        #     #         "request_three_d_secure": request_three_d_secure
        #     #     },
        #     # }
        #     # payment_method=paymentMethods.data[0]['id'],
        # )
        return web.Response(
            status=200,
            body=json.dumps(
                {
                    # "payment_method_id": f"{paymentMethods.data[0]['id']}",
                    "client_secret": f"{payment_intent.get('client_secret', None)}",
                    "ephemeral_key": f"{ephemeralKey.get('secret', None)}",
                    "customer_id": customer.data[0]["id"],
                }
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# @user_routes.post("/user/get_charging_station_info/{charger_id}/{day}")
# async def get_charging_station_info(request: web.Request) -> web.Response:
#     try:
#         data: Dict[str, Any] = await request.json()
#         if data.get("charger_id") is None:
#             return web.Response(
#                 status=400,
#                 body=json.dumps({"msg": "Invalid Parameters"}),
#                 content_type="application/json",
#             )
#         user_id = request["user"]
#         await user_dao.add_charger(user_id, data["charger_id"])
#         return web.Response(
#             status=200,
#             body=json.dumps({"msg": "Charger Successfully Added!"}),
#             content_type="application/json",
#         )
#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


@user_routes.post("/user/get_session_invoice")
async def get_session_invoice(request: web.Request) -> web.Response:
    try:
        data: Dict[str, Any] = await request.json()
        user_id = request["user"]
        session_id = data["session_id"]
        tenant_id = request["tenant_id"]
        validate_parameters(session_id, tenant_id)
        data = await user_dao.get_invoice_by_user_and_session_id(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        if not data:
            return web.Response(
                status=400,
                body=json.dumps(
                    {
                        "msg": f"""
                            Couldn't found any invoice info with
                            SessionID {session_id}
                        """
                    }
                ),
                content_type="application/json",
            )
        data.update({"is_charging_stopped": True})
        return web.Response(
            status=200, body=json.dumps(data), content_type="application/json"
        )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/save_user_token")
async def save_user_token(request: web.Request) -> web.Response:
    try:
        data: Dict[str, Any] = await request.json()
        tenant_id = request["tenant_id"]
        validate_parameters(data.get("token"), data.get("os"))
        user_id = request["user"]
        token = data["token"]
        os = data["os"]
        business_mobile_app = request["business_mobile_app"]
        LOGGER.info(f"request body {data}")
        await user_dao.save_user_token(
            token=token,
            os=os,
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "Token added Successfully!"}),
            content_type="application/json",
        )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/get_recent_charging_stations/{day}")
async def get_recent_charging_stations(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        day = request.match_info["day"]
        if day is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        tenant_id = request["tenant_id"]
        res = await user_dao.get_recent_charging_stations(
            user_id=user_id,
            day=day,
            tenant_id=tenant_id,
        )
        return web.Response(
            status=200,
            body=json.dumps({"location_ids": res}),
            # body=json.dumps({"msg": "Success", "locations": res}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/get_price_plan")
async def get_pricing_of_charger_and_user(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        data: Dict[str, Any] = await request.json()
        price_dict = {}
        charger_id = data.get("charger_id")
        connector_id = data.get("connector_id")
        user_price = await user_dao.get_user_price_for_charger(
            charger_id=charger_id, connector_id=connector_id, user_id=user_id,
            tenant_id=tenant_id
        )
        organisation_properties = await user_dao.business_details_and_properties(
            tenant_id=tenant_id
        )
        price_include_tax = bool(
            int(organisation_properties.get("price_include_tax", 0))
        )
        if not user_price:
            charger_price = await user_dao.get_charger_pricing_plan(
                charger_id=charger_id,
                connector_id=connector_id,
                tenant_id=tenant_id,
            )
            price_dict.update(
                {
                    "price": float(charger_price.get("price")),
                    "plan_type": charger_price.get("type"),
                    "price_include_tax": price_include_tax,
                    "bill_type": charger_price.get("billing_type"),
                }
            )
        else:
            price_dict.update(
                {
                    "price": float(user_price.get("price")),
                    "plan_type": user_price.get("type"),
                    "price_include_tax": price_include_tax,
                    "bill_type": user_price.get("billing_type"),
                }
            )
        return web.Response(
            status=200,
            body=json.dumps({"price": price_dict}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/get_organisation_properties")
async def get_organisation_properties(request: web.Request) -> web.Response:
    try:
        tenant_id = request["tenant_id"]
        org_properties = await app_dao.business_details_and_properties(
            tenant_id=tenant_id
        )
        if org_properties:
            return web.Response(
                status=200,
                body=json.dumps({"properties": org_properties}),
                content_type="application/json",
            )
        return web.Response(
            status=400,
            body=json.dumps(
                {
                    "msg": """
                        Organisation Properties Not Found.
                        Please provide valid org_id
                    """
                }
            ),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/get_invoice/{session_id}")
async def get_invoice(request: web.Request):
    try:
        session_id = int(request.match_info["session_id"])
        if session_id is None or session_id == "" or session_id <= 0:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        tenant_id = request["tenant_id"]
        invoice = await user_dao.get_invoice_by_session_id(
            session_id=session_id,
            tenant_id=tenant_id,
        )
        if invoice:
            return web.Response(
                status=200,
                body=json.dumps(invoice),
                content_type="application/json",
            )
        return web.Response(
            status=400,
            body=json.dumps(
                {
                    "msg": """
                        Invoice Not Found.
                        Please provide valid invoice_id.
                    """
                }
            ),
            content_type="application/json",
        )
    except ValueError as e:
        LOGGER.error(e)
        return web.Response(
            status=400,
            body=json.dumps({"msg": "Invalid Parameters"}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/sessions/")
async def get_users_sessions(request: web.Request):
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        tenant_list = await get_tenant_ids_based_on_mobile_app(
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )
        tasks = []
        combine_result = []
        sessions = []

        for tenant_id in tenant_list:
            tasks.append(user_dao.get_users_sessions(
                user_id=user_id,
                tenant_id=tenant_id,
                business_mobile_app=business_mobile_app,
            ))
        results = await asyncio.gather(*tasks)

        if results:
            for result in results:
                for sessions in result:
                    combine_result += sessions

        if combine_result:
            sessions = await user_dao.sort_history_and_arrange_by_date(
                combine_result, False
            )

        date_session_dict = {}
        final_list = []

        for session in sessions:
            start_time: datetime = session.get("start_time")
            key = start_time.date()
            session["start_date"] = str(key)
            session["start_time"] = str(session["start_time"])

            if key in date_session_dict.keys():
                date_session_dict[key].append(session)
            else:
                date_session_dict[key] = [session]

        for session_list in date_session_dict.values():
            final_list.append(session_list)

        return web.Response(
            status=200,
            body=json.dumps({"sessions": final_list}),
            content_type="application/json",
        )

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/add_stripe_payment_info/")
async def add_stripe_payment_info(request: web.Request):
    try:
        user_id = request["user"]
        data = await request.json()
        payment_id = data.get("payment_id")
        amount = data.get("amount")
        tenant_id = request["tenant_id"]
        validate_parameters(tenant_id, amount, payment_id)
        res = await user_dao.insert_stripe_payment_info(
            user_id=user_id,
            payment_id=payment_id,
            amount=amount,
            tenant_id=tenant_id,
        )
        if res:
            return web.Response(
                status=200,
                body=json.dumps(
                    {
                        "msg": """
                            Stripe payment info added successfully.
                        """
                    }
                ),
                content_type="application/json",
            )
        return web.Response(
            status=400,
            body=json.dumps(
                {
                    "msg": """
                        Couldn't add Stripe payment info try again after sometime.
                    """
                }
            ),
            content_type="application/json",
        )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/get_wallet_history/")
async def get_wallet_history(request: web.Request):
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        test = request.headers.get("test")
        payment_method = request.headers.get("payment_method")
        business_mobile_app = request["business_mobile_app"]

        tenant_id_list = await get_tenant_ids_based_on_mobile_app(
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )

        organisation_properties = {}
        if business_mobile_app:
            organisation_properties = await app_dao.get_tenants_properties(tenant_id)
        else:
            organisation_properties = await app_dao.get_enterprise_properties()

        combined_history = []
        tasks = []
        for tenant_id in tenant_id_list:
            if payment_method == "maib":
                tasks.append(user_dao.get_maib_wallet_history(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    business_mobile_app=business_mobile_app,
                ))
            elif (
                organisation_properties.get("phonepe_gateway") == "True"
                and test is not None
            ):
                tasks.append(user_dao.get_phonepe_wallet_history(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    business_mobile_app=business_mobile_app,
                ))
            else:
                tasks.append(user_dao.get_wallet_history(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    business_mobile_app=business_mobile_app,
                ))

        if tasks:
            results = await asyncio.gather(*tasks)
            for result in results:
                combined_history += result

        if combined_history:
            combined_history = await user_dao.sort_history_and_arrange_by_date(
                combined_history
            )
            return web.Response(
                status=200,
                body=json.dumps({"transactions": combined_history}),
                content_type="application/json",
            )
        else:
            return web.Response(
                status=200,
                body=json.dumps({"transactions": []}),
                content_type="application/json",
            )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# @user_routes.get("/user/send_email/")
# async def send_mail(request: web.Request):
#     try:
#         request["user"]
#         org_id = "63c42daf-1219-424b-8b5e-294e6c29604c"
#         organisation_info = await user_dao.get_organisation_detail(org_id=org_id)
#         organisation_details = await user_dao.get_organisation_properties(
#             org_id=org_id
#         )
#         invoice_details = await user_dao.get_session_invoice(session_id="55")
#         if not organisation_info or not organisation_details or not invoice_details:
#             raise Exception
#         organisation_details["vat"] = organisation_info.get("vat")
#         organisation_details["email"] = organisation_info.get("email")
#         organisation_details["org_name"] = organisation_info.get("org_name")
#         await mail.send_html_email(
#             org_details=organisation_details, invoice_details=invoice_details
#         )
#         return web.Response(
#             status=200,
#             body=json.dumps(
#                 {
#                     "msg": """
#                         Couldn't fetch wallet info try again after sometime.
#                     """
#                 }
#             ),
#             content_type="application/json",
#         )
#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )

@user_routes.get("/user/get_charging_station_details/")
async def fetch_charging_station_details(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]

        day = "monday" if request.query.get(
            "day") is None else request.query.get("day")
        charger_id = request.query.get("charger_id")
        connector_id = request.query.get("connector_id")

        validate_parameters(charger_id, connector_id)

        if not business_mobile_app:
            tenant_unique_code = request.query.get("tenant_unique_code")
            tenant_id = await app_dao.get_tenant_id_from_unique_code(tenant_unique_code)

        if not tenant_id:
            return web.Response(
                status=400,
                body=json.dumps(
                    {"msg": "Charging Station Not Found."}),
                content_type="application/json",
            )

        tenant = await app_dao.get_tenant_detail(tenant_id=tenant_id)
        if not tenant:
            return web.Response(
                status=400,
                body=json.dumps(
                    {"msg": "Charging Station Not Found."}),
                content_type="application/json",
            )

        charger = await user_dao.get_charger_detail(
            charger_id=charger_id, connector_id=connector_id, tenant_id=tenant_id
        )
        locations_id = charger.get("location_id")

        (
            location,
            amenities,
            # images,
            user_plan,
            # org_max_deposite,
            organisation_properties,
        ) = await asyncio.gather(
            user_dao.get_charger_location(locations_id, day, tenant_id),
            user_dao.get_location_amenities(locations_id, tenant_id),
            # user_dao.get_location_images(locations_id, tenant_id),
            user_dao.get_user_price_for_charger(
                user_id=user_id,
                charger_id=charger_id,
                connector_id=connector_id,
                tenant_id=tenant_id,
            ),
            # get_holding_amount_of_organisation(org_ids=loc_org_id),
            app_dao.business_details_and_properties(
                tenant_id=tenant_id
            )
        )

        # if org_max_deposite:
        #     charger["connector"]["max_amount"] = org_max_deposite.get(loc_org_id).get(
        #         charger.get("type")
        #     )

        if organisation_properties:
            charger["connector"]["currency"] = utils.get_currency_symbol(
                organisation_properties.get("currency")
            )

        if not business_mobile_app:
            properties = await app_dao.get_enterprise_properties()
            charger["connector"]["price_include_tax"] = bool(
                int(properties.get("price_include_tax", 1))
            )
        else:
            charger["connector"]["price_include_tax"] = bool(
                int(organisation_properties.get("price_include_tax", 1))
            )

        if user_plan:
            connector = charger.get("connector")
            connector["price"] = float(user_plan.get(
                "price", connector.get("price")))
            connector["bill_by"] = user_plan.get(
                "billing_type", connector.get("bill_by")
            )
            connector["plan_type"] = user_plan.get(
                "plan_type", connector.get("plan_type")
            )
            connector["apply_after"] = (user_plan.get(
                "apply_after", connector.get("apply_after")))
            connector["fixed_starting_fee"] = float(user_plan.get(
                "fixed_starting_fee", connector.get("fixed_starting_fee")))
            connector["idle_charging_fee"] = float(user_plan.get(
                "idle_charging_fee", connector.get("idle_charging_fee")))

            charger["connector"] = connector

        location["charger"] = charger
        location["amenities"] = amenities
        # location["images"] = images
        location["tenant_id"] = tenant_id

        return web.Response(
            status=200,
            body=json.dumps(location),
            content_type="application/json",
        )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/delete/")
async def delete_user(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        validate_parameters(user_id, tenant_id)
        business_mobile_app = request["business_mobile_app"]
        res = await user_dao.get_user(
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app
        )
        if not res:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "User Not Registered."}),
                content_type="application/json",
            )
        db_index = res.get("id")

        await user_dao.delete_user(
            user_id,
            tenant_id,
            db_index,
            business_mobile_app
        )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "User deleted successfully."}),
            content_type="application/json",
        )

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# @user_routes.post("/user/abc/")
# async def abc_abc(request: web.Request) -> web.Response:
#     try:
#         user_id = request["user"]
#         org_id = request.headers["organisationId"]
#         data = await request.json()
#         session_id = data.get("transaction_id")
#         session_start_time = data.get("session_start_time")
#         change_status_time = data.get("change_status_time")
#         await idle_charging_info(
#             user_id=user_id,
#             session_start_time=session_start_time,
#             change_status_time=change_status_time,
#             session_id=session_id,
#         )
#         return web.Response(
#             status=200,
#             body=json.dumps({"msg": "User idle charging processes successfully."}),
#             content_type="application/json",
#         )

#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


# @user_routes.post("/user/abc/")
# async def abc_abc(request: web.Request) -> web.Response:
#     try:
#         user_id = request["user"]
#         org_id = request.headers["organisationId"]
#         data = await request.json()
#         session_id = data.get("transaction_id")
#         session_start_time = data.get("session_start_time")
#         change_status_time = data.get("change_status_time")
#         from utils import generate_invoice

#         await generate_invoice(session_id=session_id)
#         return web.Response(
#             status=200,
#             body=json.dumps({"msg": "User idle charging processes successfully."}),
#             content_type="application/json",
#         )

#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


@user_routes.post("/user/queueactions/")
async def queue_actions(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        data = await request.json()
        location_id = int(data.get("locationId"))
        action = data.get("action")
        validate_parameters(user_id, tenant_id, location_id)
        connector_status = await user_dao.get_location_connectors_status(
            location_id=location_id, tenant_id=tenant_id,
        )
        for status in connector_status:
            if status != "Charging" and status != "Unavailable" and status != "Faulted":
                return web.Response(
                    status=400,
                    body=json.dumps(
                        {"msg": "Charger is available at the location"}),
                    content_type="applicatin/json",
                )
        if action == "join":
            join_queue(location_id, user_id)
            user_queue_number = (
                queue_number(location_id=location_id, user_id=user_id) + 1
            )

            return web.Response(
                status=200,
                body=json.dumps(
                    {"user_at_queue": True, "number": user_queue_number}),
                content_type="application/json",
            )
        elif action == "skip":
            skip_queue(location_id, user_id)
        elif action == "leave":
            leave_queue(location_id, user_id)

        queue_size = get_queue_size(location_id=location_id)
        return web.Response(
            status=200,
            body=json.dumps(
                {"msg": "Action performed Successfully", "number": queue_size}
            ),
            content_type="application/json",
        )

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/queuenumber/")
async def get_queue_number(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        location_id = int(request.query.get("locationId"))
        validate_parameters(tenant_id, location_id)
        connector_status = await user_dao.get_location_connectors_status(
            location_id=location_id, tenant_id=tenant_id
        )
        for status in connector_status:
            if status != "Charging" and status != "Unavailable" and status != "Faulted":
                return web.Response(
                    status=400,
                    body=json.dumps(
                        {"msg": "Charger is available at the location"}),
                    content_type="application/json",
                )
        user_at_queue = is_user_in_queue(
            location_id=location_id, user_id=user_id)
        user_queue_number = get_queue_size(location_id=location_id)
        if user_at_queue:
            user_queue_number = (
                queue_number(location_id=location_id, user_id=user_id) + 1
            )

        return web.Response(
            status=200,
            body=json.dumps(
                {"user_at_queue": user_at_queue, "number": user_queue_number}
            ),
            content_type="application/json",
        )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/mail_invoice/")
async def send_invoice_to_user_mail(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        data = await request.json()
        session_id = int(data.get("session_id"))
        validate_parameters(user_id, tenant_id, session_id)
        tenant_detail = await app_dao.business_details_and_properties(
            tenant_id=tenant_id
        )
        invoice_details = await user_dao.get_session_invoice(
            session_id=session_id,
            tenant_id=tenant_id,
        )
        if ((not tenant_detail) or (not invoice_details)):
            raise Exception(
                "Tenant Details/Properties or Invoice Details is empty"
            )
        business_mobile_app = request["business_mobile_app"]
        res = await user_dao.get_user_details(
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )
        receiver_email = res.get("email")
        await mail.send_plain_invoice_email(
            invoice_details=invoice_details,
            tenant_detail=tenant_detail,
            receiver_email=receiver_email,
        )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "Invoice sent to user successfully."}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/v2/estimates/")
async def get_estimates(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        charger_id = request.query["charger_id"]
        connector_id = request.query["connector_id"]
        vehicle_id = request.query["vehicle_id"]
        estimate_soc = request.query.get("estimate_soc", None)
        estimate_minutes = request.query.get("estimate_minutes", None)
        estimate_units = request.query.get("estimate_units", None)
        if not estimate_soc and not estimate_minutes and not estimate_units:
            return web.Response(
                status=400,
                body=json.dumps(
                    {"msg": "Invalid or Missing Estimate Parameter"}),
                content_type="application/json",
            )
        if not charger_id or not connector_id or not vehicle_id:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid or Missing Parameters"}),
                content_type="application/json",
            )
        organisation_details = await app_dao.business_details_and_properties(
            tenant_id=tenant_id
        )
        price_include_tax = bool(
            int(organisation_details.get("price_include_tax", 0)))
        tax_percentage = organisation_details.get("tax_percentage")
        tax_percentage = int(tax_percentage) if tax_percentage else 0
        connector_details = await user_dao.get_connector_details(
            charger_id=charger_id,
            connector_id=connector_id,
            tenant_id=tenant_id
        )
        private_plan = await user_dao.get_users_private_plan(
            user_id=user_id,
            charger_id=charger_id,
            connector_id=connector_id,
            tenant_id=tenant_id,
        )
        business_mobile_app = request["business_mobile_app"]
        if private_plan:
            connector_details["bill_by"] = private_plan["bill_by"]
            connector_details["price"] = private_plan["price"]
        vehicle_details = await user_dao.get_vehicle_details(
            vehicle_id,
            tenant_id,
            business_mobile_app
        )
        if connector_details is None or vehicle_details is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        from utils import format_time_with_leading_zeros

        bill_by = connector_details["bill_by"]
        max_output = connector_details.get("max_output")
        price = float(connector_details.get("price"))
        battery_size = vehicle_details.get("battery_size")
        range = vehicle_details.get("range")
        seconds_in_one_hr = 3600
        if bill_by == "per_minute":
            if estimate_units:
                estimate_units = float(estimate_units)
                charge_time = int(
                    (estimate_units * seconds_in_one_hr) / max_output)
                charging_cost = round(
                    (charge_time * price) / seconds_in_one_hr, 2)
                if price_include_tax:
                    total_cost = charging_cost
                    charging_cost, tax_cost = utils.calculate_base_and_tax(
                        total_amount=total_cost, tax_percentage=tax_percentage
                    )
                else:
                    tax_cost, total_cost = utils.calculate_tax_and_total(
                        base_amount=charging_cost, tax_percentage=tax_percentage
                    )
                charge_time_timedelta = datetime.timedelta(
                    seconds=int(charge_time))
                charge_time = format_time_with_leading_zeros(
                    charge_time_timedelta)
                soc_added = round((100 * estimate_units) / battery_size, 2)
                milage_added = round(
                    (estimate_units * range) / battery_size, 2)
                response = {
                    "charging_cost": charging_cost,
                    "tax_cost": tax_cost,
                    "total_cost": total_cost,
                    "soc_added": soc_added,
                    "milage_added": milage_added,
                    "charge_time": charge_time,
                    "charging_allowed": True,
                }
            elif estimate_minutes:
                estimate_minutes = int(estimate_minutes)
                estimate_seconds = int(estimate_minutes * 60)
                units_consumed = round(
                    (estimate_seconds * max_output) / seconds_in_one_hr, 2
                )
                soc_added = round((100 * units_consumed) / battery_size, 2)
                milage_added = round(
                    (units_consumed * range) / battery_size, 2)
                charging_cost = round(
                    (estimate_seconds * price) / seconds_in_one_hr, 2)
                if price_include_tax:
                    total_cost = charging_cost
                    charging_cost, tax_cost = utils.calculate_base_and_tax(
                        total_amount=total_cost, tax_percentage=tax_percentage
                    )
                else:
                    tax_cost, total_cost = utils.calculate_tax_and_total(
                        base_amount=charging_cost, tax_percentage=tax_percentage
                    )
                response = {
                    "charging_cost": charging_cost,
                    "tax_cost": tax_cost,
                    "total_cost": total_cost,
                    "soc_added": soc_added,
                    "milage_added": milage_added,
                    "units_consumed": units_consumed,
                    "charging_allowed": True,
                }
            elif estimate_soc:
                estimate_soc = float(estimate_soc)
                units_consumed = round((estimate_soc * battery_size) / 100, 2)
                milage_added = round(
                    (units_consumed * range) / battery_size, 2)
                charge_time = int((units_consumed * 3600) / max_output)
                charging_cost = round((charge_time * price) / 3600, 2)
                if price_include_tax:
                    total_cost = charging_cost
                    charging_cost, tax_cost = utils.calculate_base_and_tax(
                        total_amount=total_cost, tax_percentage=tax_percentage
                    )
                else:
                    tax_cost, total_cost = utils.calculate_tax_and_total(
                        base_amount=charging_cost, tax_percentage=tax_percentage
                    )
                charge_time_timedelta = datetime.timedelta(seconds=charge_time)
                charge_time = format_time_with_leading_zeros(
                    charge_time_timedelta)
                response = {
                    "charging_cost": charging_cost,
                    "tax_cost": tax_cost,
                    "total_cost": total_cost,
                    "milage_added": milage_added,
                    "units_consumed": units_consumed,
                    "charge_time": charge_time,
                    "charging_allowed": True,
                }
            else:
                response = {"charging_allowed": False}
        elif bill_by == "per_kWh":
            if estimate_units:
                estimate_units = float(estimate_units)
                charging_cost = round(estimate_units * price, 2)
                if price_include_tax:
                    total_cost = charging_cost
                    charging_cost, tax_cost = utils.calculate_base_and_tax(
                        total_amount=total_cost, tax_percentage=tax_percentage
                    )
                else:
                    tax_cost, total_cost = utils.calculate_tax_and_total(
                        base_amount=charging_cost, tax_percentage=tax_percentage
                    )
                soc_added = round((100 * estimate_units) / battery_size, 2)
                milage_added = round(
                    (estimate_units * range) / battery_size, 2)
                charge_time = int(
                    (estimate_units * seconds_in_one_hr) / max_output)
                charge_time_timedelta = datetime.timedelta(
                    seconds=int(charge_time))
                charge_time = format_time_with_leading_zeros(
                    charge_time_timedelta)
                response = {
                    "charging_cost": charging_cost,
                    "tax_cost": tax_cost,
                    "total_cost": total_cost,
                    "soc_added": soc_added,
                    "milage_added": milage_added,
                    "charge_time": charge_time,
                    "charging_allowed": True,
                }
            elif estimate_minutes:
                estimate_minutes = int(estimate_minutes)
                estimate_seconds = int(estimate_minutes * 60)
                units_consumed = round(
                    (estimate_seconds * max_output) / seconds_in_one_hr, 2
                )
                soc_added = round((100 * units_consumed) / battery_size, 2)
                milage_added = round(
                    (units_consumed * range) / battery_size, 2)
                charging_cost = round(units_consumed * price, 2)
                if price_include_tax:
                    total_cost = charging_cost
                    charging_cost, tax_cost = utils.calculate_base_and_tax(
                        total_amount=total_cost, tax_percentage=tax_percentage
                    )
                else:
                    tax_cost, total_cost = utils.calculate_tax_and_total(
                        base_amount=charging_cost, tax_percentage=tax_percentage
                    )
                response = {
                    "charging_cost": charging_cost,
                    "tax_cost": tax_cost,
                    "total_cost": total_cost,
                    "soc_added": soc_added,
                    "milage_added": milage_added,
                    "units_consumed": units_consumed,
                    "charging_allowed": True,
                }
            elif estimate_soc:
                estimate_soc = float(estimate_soc)
                units_consumed = round((estimate_soc * battery_size) / 100, 2)
                milage_added = round(
                    (units_consumed * range) / battery_size, 2)
                charging_cost = round(units_consumed * price, 2)
                if price_include_tax:
                    total_cost = charging_cost
                    charging_cost, tax_cost = utils.calculate_base_and_tax(
                        total_amount=total_cost, tax_percentage=tax_percentage
                    )
                else:
                    tax_cost, total_cost = utils.calculate_tax_and_total(
                        base_amount=charging_cost, tax_percentage=tax_percentage
                    )
                charge_time = int((units_consumed * 3600) / max_output)
                charge_time_timedelta = datetime.timedelta(seconds=charge_time)
                charge_time = format_time_with_leading_zeros(
                    charge_time_timedelta)
                response = {
                    "charging_cost": charging_cost,
                    "tax_cost": tax_cost,
                    "total_cost": total_cost,
                    "milage_added": milage_added,
                    "units_consumed": units_consumed,
                    "charge_time": charge_time,
                    "charging_allowed": True,
                }
            else:
                response = {"charging_allowed": False}
        else:
            response = {"charging_allowed": False}
        return web.Response(
            status=200, body=json.dumps(response), content_type="application/json"
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/notification_config/")
async def get_notification_config(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        charger_type = request.query["charger_type"]
        response = await user_dao.get_notification_config(
            charger_type=charger_type, user_id=user_id, tenant_id=tenant_id
        )
        if not response:
            response = {"notification_type": "NONE", "notification_value": "0"}
        return web.Response(
            status=200, body=json.dumps(response), content_type="application/json"
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/set_notification_config/")
async def set_notification_config(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        data = await request.json()
        charger_type = data.get("charger_type")
        # notification types = duration/soc/cost
        notification_type = data.get("notification_type")
        notification_value = data.get("notification_value")
        if notification_type == "NONE":
            response = await user_dao.delete_notification_config(
                user_id=user_id,
                charger_type=charger_type,
                tenant_id=tenant_id,
            )
            return web.Response(
                status=200, body=json.dumps(response), content_type="application/json"
            )
        else:
            response = await user_dao.upsert_notification_config(
                charger_type=charger_type,
                notification_type=notification_type,
                notification_value=notification_value,
                user_id=user_id,
                tenant_id=tenant_id,
            )

            return web.Response(
                status=200, body=json.dumps(response), content_type="application/json"
            )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/apply_coupon/")
async def apply_coupon(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        request.headers["organisationId"]
        data = await request.json()
        offer_code = data.get("offer_code")
        tenant_id = request["tenant_id"]
        response = await user_dao.apply_coupon(
            offer_code=offer_code,
            tenant_id=tenant_id,
            user_id=user_id
        )
        return web.Response(
            status=200, body=json.dumps(response), content_type="application/json"
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/transactionId/")
async def get_transaction_id_for_user(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]

        merchant_transaction_id = uuid.uuid4()

        await user_dao.insert_merchant_transaction_id(
            user_id,
            merchant_transaction_id,
            tenant_id
        )

        return web.Response(
            status=200,
            content_type="application/json",
            body=json.dumps(
                {"merchantTransactionId": str(merchant_transaction_id)}),
        )

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/phonepepending/")
async def phonepe_pending_transaction(request: web.Request) -> web.Response:
    try:
        request["user"]
        body = await request.json()
        tenant_id = request["tenant_id"]
        merchant_id = body.get("merchantId")
        merchant_transaction_id = body.get("merchantTransactionId")
        amount = body.get("amount")

        if merchant_id is None or merchant_transaction_id is None or amount is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        await user_dao.update_phonepe_transaction(
            merchant_id=merchant_id,
            merchant_transaction_id=merchant_transaction_id,
            amount=amount,
            tenant_id=tenant_id,
        )

        return web.Response(
            status=200,
            body=json.dumps({"message": "Transaction Updated successfully!"}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


# @user_routes.get("/user/idle_fee_buffer_info/{session_id}")
# async def idle_fee_buffer(request: web.Request) -> web.Response:
#     try:
#         request["user"]
#         request.headers["organisationId"]
#         session_id = int(request.match_info.get("session_id"))
#         if not session_id:
#             return web.Response(
#                 status=400,
#                 body=json.dumps({"msg": "Invalid Parameters"}),
#                 content_type="application/json",
#             )
#         session_paramter_info = await user_dao.get_price_plan_by_session_parameter(
#             session_id=session_id
#         )
#         check_empty_info(session_paramter_info)
#         res = await user_dao.get_pricing_plan(
#             price_id=session_paramter_info.get("price_id")
#         )
#         data = {
#             "apply_after": res.get("apply_after"),
#             "idle_charging_fee": res.get("idle_charging_fee"),
#         }
#         check_empty_info(data)
#         return web.Response(
#             status=200,
#             body=json.dumps(data),
#         )
#     except Exception as e:
#         LOGGER.error(e)
#         return web.Response(
#             status=500,
#             body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
#             content_type="application/json",
#         )


@user_routes.get("/user/get_idle_fee_info/{session_id}")
async def get_idle_info(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        session_id = int(request.match_info.get("session_id"))
        tenant_id = request["tenant_id"]
        validate_parameters(session_id, tenant_id)
        data = await get_idle_details(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        check_empty_info(data)
        print(data)
        return web.Response(
            status=200,
            body=json.dumps(data[tenant_id][session_id]),
        )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/get_ongoing_idle_sessions/")
async def get_ongoing_idle_sessions(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]

        tenant_id_list = await get_tenant_ids_based_on_mobile_app(
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )

        tasks1 = []
        tasks2 = []
        sessions = {}
        sessions_dict = {}

        for tenant_id in tenant_id_list:
            tasks1.append(
                user_dao.get_ongoing_idle_sessions(user_id, tenant_id)
            )
            sessions_dict[tenant_id] = {}

        results_sessions = await asyncio.gather(*tasks1)

        for result in results_sessions:
            sessions.update(result)

        for tenant_id, sessions in sessions.items():
            for session in sessions:
                tasks2.append(get_idle_details(
                    session_id=session,
                    user_id=user_id,
                    tenant_id=tenant_id,
                ))

        results = await asyncio.gather(*tasks2)

        for result in results:
            for tenant_id, sessions in result.items():
                sessions_dict[tenant_id].update(sessions)

        return web.Response(
            status=200,
            body=json.dumps(sessions_dict),
        )

    except ParameterMissing as e:
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/sample_notification/")
async def test_notification(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        await fcm.send_notification(
            title=None,
            body=None,
            user_id=user_id,
            tenant_id=tenant_id,
            data={
                "action": "notification_limit_reached",
                "user_id": user_id,
                "body": "Battery percentage exceeds%",
                "title": "Session Target Reached.",
            },
        )
        return web.Response(
            status=200,
            body=json.dumps({}),
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/minimum_balance/")
async def minimum_balance(request: web.Request) -> web.Response:
    try:
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        properties = {}

        if business_mobile_app:
            properties = await app_dao.business_details_and_properties(
                tenant_id=tenant_id)
        else:
            properties = await app_dao.enterprise_settings_and_properties()

        return web.Response(
            status=200,
            body=json.dumps({
                "minimumWalletBalance": str(properties.get("minimum_wallet_balance", 0))
            }),
        )

    except ParameterMissing as e:
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/refund/")
async def refundstripeauthorization(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        data = await request.json()
        data.get("reason", "requested_by_customer")
        charger_id = data.get("charger_id", None)
        connector_id = data.get("connector_id", None)
        tenant_id = request["tenant_id"]
        validate_parameters(charger_id, connector_id, tenant_id)
        # Note: stripe key is set in one of the
        # previous api keys because it is a global object
        res = await user_dao.get_latest_payment_intent_id(
            charger_id, connector_id, user_id, tenant_id
        )
        payment_intent_id = res.get("payment_intent_id", None)
        if payment_intent_id:
            refund_response = stripe.PaymentIntent.cancel(payment_intent_id)
            if refund_response.status == "canceled":
                return web.Response(
                    status=200,
                    body=json.dumps({"msg": "Refund initiated successfully!"}),
                    content_type="application/json",
                )
            else:
                return (
                    web.Response(
                        status=400,
                        body=json.dumps(
                            {"msg": "Refund failed", "status": refund_response.status}
                        ),
                    ),
                )
    except ParameterMissing as e:
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.get("/user/plugsharelink/{charger_id}")
async def plugsharelink(request: web.Request) -> web.Response:
    try:
        request["user"]
        tenant_id = request["tenant_id"]
        charger_id = str(request.match_info.get("charger_id"))
        validate_parameters(tenant_id, charger_id)
        link = await user_dao.get_plugshare_link(
            charger_id=charger_id,
            tenant_id=tenant_id,
        )
        if link != "":
            return web.Response(
                status=200,
                body=json.dumps({"link": link}),
            )
        return web.Response(
            status=400,
            body=json.dumps(
                {"msg": f"No link found for charger id {charger_id}"}),
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/pay/")
async def pay(request: web.Request):

    try:
        body = await request.json()
        user_id = request["user"]
        tenant_id = request["tenant_id"] if (
            request["tenant_id"] != "") else "enterprise"
        amount = body.get("amount")
        currency = body.get("currency")
        if (amount is None):
            return web.Response(
                status=400,
                body=json.dumps(
                    {"msg": f"Invalid parameters passed!. Please send correct parameters"})
            )

        merchant_name = config["MERCHANT_NAME"]
        paywall_secret_key = config["PAYWALL_SECRET_KEY"]
        payment_gateway = "payzone"
        merchant_payment_id = generate_unique_key(key=payment_gateway)

        payment_time = time.time()
        charge_properties = {
            "tenant_id": tenant_id if (tenant_id != "") else "enterprise"
        }

        payload = {
            "merchantAccount": merchant_name,
            "timestamp": int(payment_time),
            "skin": "vps-1-vue",
            "customerId": user_id,
            "customerCountry": "MA",
            "customerLocale": "en_US",
            "price": body.get("amount"),
            "currency": "MAD",
            "description": "Wallet top-up for EVPlug",
            "chargeId": str(merchant_payment_id),
            "mode": "DEEP_LINK",
            "paymentMethod": "CREDIT_CARD",
            "chargeProperties": charge_properties,
            "callbackUrl": str("https://app-server.bornerecharge.ma/server/payzone/callback/"),
            'flowCompletionUrl': str("https://app-server.bornerecharge.ma/server/payzone/flowback/")
        }

        json_payload_str = json.dumps(
            payload, separators=(',', ':'), sort_keys=False)
        signature = hashlib.sha256(
            (paywall_secret_key + json_payload_str).encode('utf-8')).hexdigest()

        response_dict = {
            "json_payload": payload,
            "signature": signature
        }

        await user_dao.insert_payment_transaction(
            merchantPaymentId=merchant_payment_id,
            currency=currency,
            amount=amount,
            transactionTime=datetime.utcnow().isoformat(),
            user_id=user_id,
            tenant_id=tenant_id,
            paymentGateway=payment_gateway,
            status='INITIATED'
        )

        return web.Response(
            status=200,
            body=json.dumps(response_dict, separators=(
                ',', ':'), sort_keys=False),
            content_type="application/json",
        )
    except Exception as e:
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal server error occured with error {e}"})
        )


@user_routes.post("/user/order/")
async def razopaycreateorder(request: web.Request):
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        data = await request.json()

        amount = data.get("amount", None)
        currency = data.get("currency", None)
        is_prod = data.get("is_prod", False)
        razorpay_keys = {}
        organisation_properties = await user_dao.business_details_and_properties(
            tenant_id=tenant_id
        )
        if (is_prod):
            razorpay_keys = organisation_properties.get("razorpay_prod_keys")
        else:
            razorpay_keys = organisation_properties.get("razorpay_test_keys")

        if (amount is None) or (currency is None):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )

        # Note: stripe key is set in one of the
        # previous api keys because it is a global object
        order_id, msg = await razorpay.create_order(
            amount=amount,
            currency=currency,
            razorpay_keys=json.loads(razorpay_keys)
        )

        await user_dao.insert_payment_transaction(
            merchantPaymentId=order_id,
            currency=currency,
            amount=amount,
            transactionTime=datetime.utcnow().isoformat(),
            user_id=user_id,
            tenant_id=tenant_id,
            paymentGateway='Razorpay',
            status='PAYMENT_INITIATED'
        )
        return web.Response(
            status=200,
            body=json.dumps(
                {"msg": msg, "order_id": order_id}),
            content_type="application/json",
        )

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@user_routes.post("/user/razorpaycallbackv2/")
async def razorpaycallback(request: web.Request):
    try:
        body = await request.json()
        tenant_id = request["tenant_id"]
        user_id = request["user"]
        status = body.get("code")
        amount_added = body.get("amount_added")
        data = body.get("data")
        is_prod = body.get("is_prod", False)
        LOGGER.info(f"razorpay callback data {data}")
        razorpay_order_id = data.get("razorpay_order_id", "N/A")
        razorpay_payment_id = data.get("razorpay_payment_id", "N/A")
        razorpay_signature = data.get("razorpay_signature", "N/A")

        success = False
        message = "Transaction Failed"
        state = "FAILED"
        razorpay_keys = {}
        organisation_properties = await user_dao.business_details_and_properties(tenant_id)
        if (is_prod):
            razorpay_keys = organisation_properties.get("razorpay_prod_keys")
        else:
            razorpay_keys = organisation_properties.get("razorpay_test_keys")

        signature = utils.generate_signature(
            order_id=razorpay_order_id,
            razorpay_payment_id=razorpay_payment_id,
            secret=json.loads(razorpay_keys).get("API_SECRET")
        )

        if status == "PAYMENT_SUCCESS" and signature == razorpay_signature:

            user_details_dict = await user_dao.get_wallet_balance(user_id)
            current_balance = user_details_dict["wallet_balance"]
            new_balance = float(int(amount_added) / 100) + float(
                current_balance
            )
            await user_dao.update_wallet_balance(
                new_balance=new_balance,
                user_id=user_id,
            )
            success = True
            message = "Transaction Success"
            state = "COMPLETED"

        await user_dao.update_payment_transaction(
            status=state,
            merchantPaymentId=razorpay_order_id,
            paymentGatewayPaymentId=razorpay_payment_id,
            paymentType="NA",
            paymentMethod="NA",
            data=json.dumps(data),
            tenant_id=tenant_id
        )
        return web.Response(
            status=200,
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )
