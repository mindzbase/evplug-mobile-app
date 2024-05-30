import json
import logging

from aiohttp import web

from dao import user_dao
from dao.app_dao import does_business_have_mobile_app
from dao.user_dao import validate_token as verify_user
from errors.mysql_error import MissingObjectOnDB
from utils import validate_parameters

LOGGER = logging.getLogger("server")
vehicle_routes = web.RouteTableDef()


@vehicle_routes.get("/vehicles/get_vehicles")
async def get_all_vehicles(request: web.Request) -> web.Response:
    try:
        tenant_id = request.headers["tenant_id"]
        business_mobile_app = await does_business_have_mobile_app(tenant_id)
        vehicles = await user_dao.get_all_vehicles(business_mobile_app, tenant_id)

        return web.Response(
            status=200,
            body=json.dumps(vehicles),
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


@vehicle_routes.get("/vehicles/get_vehiclesv2")
async def get_all_vehicles_v2(request: web.Request) -> web.Response:
    try:
        tenant_id = request.headers.get('tenant_id')
        enterprise_mobile_app = request.headers.get(
            "enterprise_mobile_app", False)
        business_mobile_app = False if enterprise_mobile_app else True
        vehicles = await user_dao.get_all_vehiclesv2(business_mobile_app, tenant_id)

        return web.Response(
            status=200,
            body=json.dumps(vehicles),
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


@vehicle_routes.post("/vehicles/default")
async def set_default_vehicle(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        vehicle_id = data.get("vehicle_id")
        user_id = data.get("user_id")
        tenant_id = request.headers["tenant_id"]
        business_mobile_app = await does_business_have_mobile_app(tenant_id)
        validate_parameters(vehicle_id, user_id,
                            tenant_id, business_mobile_app)
        res = await verify_user(user_id=user_id)
        if not res:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid user_id"}),
                content_type="application/json",
            )
        result = await user_dao.get_user_vehicle(
            user_id=user_id,
            vehicle_id=vehicle_id,
            business_mobile_app=business_mobile_app,
            tenant_id=tenant_id,
        )
        if result:
            await user_dao.set_default_vehicle(
                user_id=user_id,
                vehicle_id=vehicle_id,
                tenant_id=tenant_id,
                business_mobile_app=business_mobile_app,
            )
        else:
            await user_dao.insert_default_vehicle(
                user_id=user_id,
                vehicle_id=vehicle_id,
                business_mobile_app=business_mobile_app,
                tenant_id=tenant_id,
            )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "Default vehicle is set sucessfully."}),
            content_type="application/json",
        )

    except MissingObjectOnDB as e:
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
