from __future__ import annotations

import json
import logging
from typing import Any

from aiohttp import web

from dao import firebase_dao, user_dao
from errors.mysql_error import ParameterMissing
from utils import validate_parameters

LOGGER = logging.getLogger("server")
session_routes = web.RouteTableDef()


@session_routes.post("/session/data")
async def session_hook(request: web.Request) -> web.Response:
    try:
        data: dict[str, Any] = await request.json()
        tenant_id = request["tenant_id"]
        user_id = request["user"]
        session_id = data["session_id"]
        charger_id = data["charger_id"]
        await user_dao.update_new_charging_session(
            user_id=user_id,
            session_id=session_id,
            charger_id=charger_id,
            tenant_id=tenant_id,
        )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "Session Updated Successfully!"}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@session_routes.get("/session/notification_config/")
async def get_notification_config(request: web.Request) -> web.Response:
    try:
        request["user"]
        tenant_id = request["tenant_id"]
        session_id = request.query["session_id"]
        validate_parameters(session_id)
        response = await firebase_dao.get_session_notification(session_id, tenant_id)
        if not response:
            response = {"notification_type": "NONE", "notification_value": "0"}
        return web.Response(
            status=200,
            body=json.dumps(response),
            content_type="application/json",
        )

    except ParameterMissing as e:
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@session_routes.post("/session/set_notification_config/")
async def set_notification_config(request: web.Request) -> web.Response:
    try:
        request["user"]
        tenant_id = request["tenant_id"]
        data = await request.json()
        session_id = data.get("session_id")
        notification_type = data.get("notification_type")  # (duration/soc/cost)
        notification_value = data.get("notification_value")
        validate_parameters(session_id, notification_type, notification_value)

        await firebase_dao.delete_sent_notification_of_session(session_id, tenant_id)
        response = await firebase_dao.upsert_notification_config(
            session_id,
            notification_type,
            notification_value,
            tenant_id
        )

        return web.Response(
            status=200,
            body=json.dumps(response),
            content_type="application/json",
        )

    except ParameterMissing as e:
        return e.jsonResponse()

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )
