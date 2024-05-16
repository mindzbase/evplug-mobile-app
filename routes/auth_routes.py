from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timedelta
from typing import Any

from aiohttp import web

import utils
from dao import auth_dao, user_dao
from dao.app_dao import (
    get_user_login_session,
    insert_login_session_date,
    set_role_of_new_user,
    update_session_expiry_time,
)
from errors.mysql_error import ParameterMissing
from html_templates import verified_html
from sms import send_otp, verify_otp
from websocket import send_message_to_client

LOGGER = logging.getLogger("server")
auth_routes = web.RouteTableDef()


@auth_routes.post("/auth/login")
async def login(
    request: web.Request,
) -> web.Response:
    try:
        data: dict[str, Any] = await request.json()
        if data.get("email") is None or data.get("password") is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )

        email = data["email"]
        (uuid, stored_password) = await auth_dao.check_if_user_exists(email)
        if stored_password is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "User doesn't exists. Please signup"}),
                content_type="application/json",
            )
        if utils.check_password(data["password"], stored_password):
            return web.Response(
                status=200,
                body=json.dumps({"msg": "Login successfully"}),
                content_type="application/json",
                headers={"Authorization": f"Token {uuid}"},
            )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "Incorrect username or password"}),
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


@auth_routes.post("/auth/signup")
async def add_user_details(request: web.Request) -> web.Response:
    try:
        data: dict[str, Any] = await request.json()
        if (
            data.get("name") is None
            or data.get("email") is None
            or data.get("os") is None
            or data.get("token") is None
            or data.get("phone") is None
            or data.get("address") is None
        ):
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        name = data["name"]
        email = data["email"]
        os = data["os"]
        token = data["token"]
        phone = data["phone"]
        address = data["address"]
        user_id = await auth_dao.create_new_user(
            name=name,
            email=email,
            os=os,
            token=token,
            phone=phone,
            address=address,
            tenant_id=request["tenant_id"],
            business_mobile_app=request["business_mobile_app"]
        )
        await insert_login_session_date(
            user_id=user_id,
            business_mobile_app=request["business_mobile_app"],
            tenant_id=request["tenant_id"],
            expiry_date=datetime.utcnow() + timedelta(days=7),
        )
        await set_role_of_new_user(
            user_id=user_id,
            business_mobile_app=request["business_mobile_app"],
            tenant_id=request["tenant_id"],
        )
        return web.Response(
            status=200,
            body=json.dumps(
                {"msg": "User added Successfully!", "user_id": str(user_id)},
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


@auth_routes.get("/auth/get_details_with_fid/")
async def get_user_details_from_fid(request: web.Request) -> web.Response:
    try:
        fid = request.query["fid"]
        if fid is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        user_id = await user_dao.get_user_id_from_fid(fid=fid)
        if user_id is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        user_details_dict = await user_dao.get_user_details_with_user_id(
            user_id=user_id,
        )

        if user_details_dict is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "No user found!"}),
                content_type="application/json",
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


@auth_routes.get("/auth/user_verification")
async def user_verification(request: web.Request) -> web.Response:
    try:
        token = request.query["token"]

        if not token:
            return web.Response(
                status=500,
                body=json.dumps({"msg": "Missing Token ID"}),
                content_type="application/json",
            )

        decoded_string_bytes = base64.b64decode(token)
        decoded_string = decoded_string_bytes.decode("ascii")
        decoded_string_list = decoded_string.split("&")
        user_id = decoded_string_list[0]
        # mail_verification_token = decoded_string_list[1]
        LOGGER.info(decoded_string)

        (
            user_id,
            name,
            email,
            is_email_verified,
        ) = await user_dao.get_user_verification_details(user_id)
        if user_id is None or is_email_verified:
            return web.Response(
                status=500,
                body=json.dumps({"msg": "Invalid Token ID"}),
                content_type="application/json",
            )

        (verification_token, expire_time) = await user_dao.get_token_details(user_id)
        if verification_token != token:
            return web.Response(
                status=500,
                body=json.dumps({"msg": "Invalid Token ID"}),
                content_type="application/json",
            )
        if expire_time >= datetime.utcnow():
            tasks = await asyncio.gather(
                user_dao.get_organisation_of_user(user_id=user_id),
                user_dao.verify_user(user_id),
                send_message_to_client(
                    key=user_id,
                    tenant_id=request['tenant_id'],
                    event_name="email_verification",
                    data={"isEmailVerified": True},
                ),
            )
            organisation = tasks[0]
            primary_color = organisation.get("primary_color")
            org_name = organisation.get("org_name")
            logo_url = organisation.get("logo_url")
            html = verified_html(
                primary_color=primary_color,
                logo_url=logo_url,
                user_email=email,
                org_name=org_name,
            )
            return web.Response(
                status=200,
                body=html,
                content_type="text/html",
            )
        else:
            return web.Response(
                status=500,
                body=json.dumps({"msg": "Token ID Expired"}),
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


@auth_routes.post("/auth/verify_otp/")
async def verify_send_otp(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        phone = data.get('phone')
        otp = data.get('otp')
        reference_id = data.get('reference_id')
        utils.validate_parameters(phone, otp, reference_id)
        response = await verify_otp(
            destination_number=phone,
            otp=otp,
            reference_id=reference_id,
            tenant_id=request["tenant_id"],
            business_mobile_app=request["business_mobile_app"]
        )
        user_id = response.get('user_id')
        res = await get_user_login_session(
            user_id=user_id,
            tenant_id=request["tenant_id"],
            business_mobile_app=request["business_mobile_app"]
        )
        if res:
            await update_session_expiry_time(
                user_id=user_id,
                new_expiry_date=(datetime.utcnow() + timedelta(days=7)),
                tenant_id=request["tenant_id"],
                business_mobile_app=request["business_mobile_app"]
            )
        else:
            await insert_login_session_date(
                user_id=user_id,
                expiry_date=(datetime.utcnow() + timedelta(days=7)),
                tenant_id=request["tenant_id"],
                business_mobile_app=request["business_mobile_app"]
            )
        return web.Response(
            status=200,
            body=json.dumps(response),
            content_type="application/json",
        )

    except ParameterMissing:
        return web.Response(
            status=400,
            content_type="application/json"
        )

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@auth_routes.post("/auth/send_verification_otp/")
async def send_verification_otp(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        phone = data.get('phone')
        utils.validate_parameters(phone)
        response = await send_otp(
            destination_number=phone,
            tenant_id=request["tenant_id"],
            business_mobile_app=request["business_mobile_app"],
        )
        return web.Response(
            status=200,
            body=json.dumps({
                "msg": response.get("msg"),
                "status_code": response.get("status_code"),
                "reference_id": response.get("reference_id")
            }),
            content_type="application/json",
        )
    except ParameterMissing as e:
        LOGGER.error(e)
        return web.Response(
            status=400,
            body=json.dumps({
                "msg": "Missing Phone number",
            }),
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


@auth_routes.get("/auth/get_details_with_userid/")
async def get_user_details_from_userid(request: web.Request) -> web.Response:
    try:
        fid = request.query["user_id"]
        if fid is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        user_id = fid
        if user_id is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        user_details_dict = await user_dao.get_user_details_with_user_id(
            user_id=user_id,
            tenant_id=request["tenant_id"],
            business_mobile_app=request["business_mobile_app"]
        )

        if user_details_dict is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "No user found!"}),
                content_type="application/json",
            )
        user_details_dict["isEmailVerified"] = True

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
