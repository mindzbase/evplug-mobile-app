from __future__ import annotations

import base64
import hashlib
import json
import logging
import math
from datetime import datetime
from typing import Any, Dict
import asyncio
from aiohttp import ClientConnectorError, web
from dateutil.parser import parse

import fcm
from service_layers.app_layer import get_tenant_ids_based_on_mobile_app
from service_layers.rfid_layer import get_rfid_of_user
import utils
from dao import firebase_dao, user_dao
from dao.app_dao import business_details_and_properties, does_business_have_mobile_app, get_enterprise_properties

# from dao.app_dao import get_group_plans
from errors.mysql_error import MissingObjectOnDB, ParameterMissing
from html_templates import get_invoice_html
from ocpp_server import remote_stop, send_phonepe_request
from service_layers.FN_layer import send_firebase_notification_if_not_sent
from smart_queue import (
    check_if_queue_is_present,
    # get_first_user_in_queue,
    # rearrange_queue,
    start_queue_operations,
)
from utils import (
    calculate_base_and_tax,
    calculate_cost,
    calculate_tax_and_total,
    check_object_existence,
    create_pdf,
    get_value_without_tax,
    idle_charging_info_and_send_invoice,
    stop_charging,
    validate_parameters,
)

# from websocket import remove_connection
from websocket import send_message_to_client

LOGGER = logging.getLogger("server")
ocpp_routes = web.RouteTableDef()


@ocpp_routes.post("/server/check_wallet_balance/")
async def check_wallet_balance(request: web.Request) -> web.Response:
    try:
        data: dict[str, Any] = await request.json()
        id_tag = data.get("id_tag")
        user_id = data.get("user_id")
        if user_id is None or id_tag is None:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        if id_tag is not None:
            user_id, organisation_id = await user_dao.get_user_from_id_tag(
                id_tag=id_tag,
            )
        res = await user_dao.get_wallet_balance(user_id=user_id)
        wallet_balance = res.get("wallet_balance", 0)
        res = await user_dao.get_user_details_with_user_id(user_id=user_id)
        org_id = res.get("org_id")
        res = await user_dao.get_organisation_properties(org_id=org_id)

        has_mobile_app = None
        minimum_wallet_balance = None

        for ele in res:
            if ele["parameter_key"] == "has_mobile_app":
                has_mobile_app = bool(ele["parameter_value"])
            if ele["parameter_key"] == "minimum_wallet_balance":
                minimum_wallet_balance = float(ele["parameter_value"])

        if has_mobile_app is None:
            return web.Response(
                status=400,
                body=json.dumps(
                    {
                        "msg": "Couldn't fetch organisation has_mobile_app property",
                        "is_enough_wallet_balance": False,
                    },
                ),
                content_type="application/json",
            )

        if has_mobile_app is False:
            org_details = await user_dao.get_parent_org_id(org_id=org_id)
            parent_org_id = org_details.get(
                "parent_org_id") if org_details else None
            if parent_org_id:
                res = await user_dao.get_organisation_properties(org_id=parent_org_id)
                for ele in res:
                    if ele["parameter_key"] == "minimum_wallet_balance":
                        minimum_wallet_balance = float(ele["parameter_value"])

        if minimum_wallet_balance is None:
            return web.Response(
                status=400,
                body=json.dumps(
                    {
                        "msg": "Couldn't fetch organisation minimum balance property",
                        "is_enough_wallet_balance": False,
                    },
                ),
                content_type="application/json",
            )

        if wallet_balance >= minimum_wallet_balance:
            return web.Response(
                status=200,
                body=json.dumps(
                    {"msg": "start_charging", "is_enough_wallet_balance": True},
                ),
                content_type="application/json",
            )
        else:
            balance = minimum_wallet_balance - wallet_balance
            return web.Response(
                status=400,
                body=json.dumps(
                    {
                        "msg": f"""
                            Not enough wallet balance.
                            Minimum amount {minimum_wallet_balance} is required,
                            Please add {balance} more.
                        """,
                        "is_enough_wallet_balance": False,
                        "balance_to_add": balance,
                    },
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


@ocpp_routes.post("/server/set_session_parameters/")
async def set_session_parameters(request: web.Request) -> web.Response:
    try:
        data: dict[str, Any] = await request.json()
        session_id = data.get("session_id")
        tenant_id = data.get("tenant_id")
        charger_id = data.get("charger_id")
        connector_id = data.get("connector_id")
        id_tag = data.get("id_tag")
        vehicle_id = data.get("vehicle_id")
        # TODO: add column have_mobile_app boolean field
        utils.validate_parameters(
            session_id,
            tenant_id,
            charger_id,
            connector_id,
            id_tag,
        )
        business_mobile_app = await does_business_have_mobile_app(tenant_id)
        user_id = await user_dao.get_user_from_id_tag(
            id_tag=id_tag,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app
        )
        LOGGER.info(user_id)
        check_object_existence(user_id, "User Rfid Link")

        user = await user_dao.get_wallet_balance(
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )
        LOGGER.info(user)
        check_object_existence(user, "User")
        wallet_balance = float(user.get("wallet_balance", 0))

        # add is_default boolean column user_vehicles table
        if vehicle_id is None:
            vehicle_id = await user_dao.get_user_default_vehicle(
                user_id=user_id,
                tenant_id=tenant_id,
                business_mobile_app=business_mobile_app,
            )

        price_detail = await user_dao.get_price_plan_of_user(
            user_id, charger_id, connector_id, tenant_id
        )
        apply_after = price_detail["apply_after"]
        fixed_starting_fee = price_detail["fixed_starting_fee"]
        idle_charging_fee = price_detail["idle_charging_fee"]
        billing_type = price_detail["billing_type"]
        price = float(price_detail["price"])
        plan_id = price_detail['id']
        plan_type = price_detail["type"]

        total_minutes = 0
        total_energy = 0

        if billing_type == "per_minute":
            total_minutes = 120 if (price == 0) else math.floor(
                wallet_balance / price)
            stop_charging_by = "duration_in_minutes"
        elif billing_type == "per_kWh":
            total_energy = 45 if (price == 0) else (wallet_balance / price)
            stop_charging_by = "max_energy_consumption"

        await user_dao.add_session_paramters(
            id_tag=id_tag,
            charger_id=charger_id,
            connector_id=connector_id,
            stop_charging_by=stop_charging_by,
            session_id=session_id,
            vehicle_id=vehicle_id,
            duration_in_minutes=total_minutes,
            price=price,
            plan_type=plan_type,
            total_energy=total_energy,
            price_id=plan_id,
            billing_by=billing_type,
            tenant_id=tenant_id,
            user_id=user_id,
            apply_after=apply_after,
            fixed_starting_fee=fixed_starting_fee,
            idle_charging_fee=idle_charging_fee,
        )

        await send_message_to_client(
            key=user_id,
            tenant_id=tenant_id,
            event_name="session_id",
            data={"session_id": session_id, "tenant_id": tenant_id},
            business_mobile_app=business_mobile_app,
        )
        # res = await user_dao.get_latest_payment_intent_id(
        #     charger_id, connector_id, user_id
        # )
        # payment_intent_id = res.get("payment_intent_id", None)
        # if payment_intent_id:
        #     await user_dao.insert_session_payment_intent_mapping(
        #         session_id=session_id, payment_intent_id=payment_intent_id
        #     )
        await fcm.send_notification(
            title=f"Charging started successfully on charger {charger_id}",
            body="tap here to view your session details",
            user_id=user_id,
            data={"action": "start_charging", "session_id": session_id},
        )
        # location_id = await user_dao.charger_location_id(
        #     charger_id=charger_id
        # )
        # rearrange_queue(location_id)
        return web.Response(
            status=200,
            body=json.dumps(
                {"msg": "session paramters are sucessfully added."}),
            content_type="application/json",
        )
    except MissingObjectOnDB as e:
        LOGGER.error(e.msg)
        return e.jsonResponse
    except ParameterMissing as e:
        LOGGER.error(e.msg)
        return e.jsonResponse
    except Exception as e:
        LOGGER.error(e, stacklevel=10, stack_info=True)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@ocpp_routes.post("/server/session_finished/")
async def session_finished(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        session_id = data.get("transaction_id")
        tenant_id = data.get("tenant_id")
        validate_parameters(session_id, tenant_id)
        business_mobile_app = await does_business_have_mobile_app(tenant_id)
        res = await user_dao.get_session_detail(
            session_id=session_id,
            tenant_id=tenant_id,
        )
        id_tag = res.get("start_id_tag")
        charger_id = res.get("charger_id")
        # connector_id = res.get("connector_id")
        user_id = await user_dao.get_user_from_id_tag(
            id_tag=id_tag,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app
        )
        event_name = "stop_charging"
        data = {"session_id": session_id, "tenant_id": tenant_id}
        LOGGER.info({"key": user_id, "event_name": event_name, "data": data})
        await send_message_to_client(
            key=user_id,
            tenant_id=tenant_id,
            event_name="stop_charging",
            data=data,
            business_mobile_app=business_mobile_app
        )
        await fcm.send_notification(
            title="Session Completed",
            body=f"Charging stopped on charger {charger_id}",
            user_id=user_id,
        )
        # location_id = await user_dao.charger_location_id(charger_id=charger_id)
        # LOGGER.info("location id " + str(location_id))
        # if (
        #     org_id == "a4989bb4-a835-4093-a418-cd4c2b9a10c4"
        #     and check_if_queue_is_present(location_id=location_id)
        # ):
        #     LOGGER.info("queue is present")
        #     start_queue_operations(
        #         location_id=location_id,
        #         charger_id=charger_id,
        #         connector_id=connector_id,
        #     )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "notification sent successfully."}),
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


async def initiate_remote_stop(
    session_id, id_tag, user_id, tenant_id, business_mobile_app
):
    if session_id:
        (is_stopped, msg) = await remote_stop(
            session_id=session_id,
            stop_id_tag=id_tag,
            tenant_id=tenant_id,
        )
        if not is_stopped:
            await fcm.send_notification(
                title="Failed!",
                body="Automatic remote stop failed, User have to stop charging manually",  # noqa
                user_id=user_id,
            )
        elif is_stopped:
            await send_message_to_client(
                key=user_id,
                event_name="stop_charging",
                data={"session_id": session_id, "tenant_id": tenant_id},
                tenant_id=tenant_id,
                business_mobile_app=business_mobile_app
            )
    return


@ocpp_routes.post("/server/generate_invoice/")
async def get_pdf(request: web.Request) -> web.Response:
    try:
        req_body = await request.json()
        session_id = req_body.get("session_id", None)
        org_id = req_body.get("organisationId", None)
        if not session_id or not org_id:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        pdf = await generate_invoice(session_id=session_id, org_id=org_id)
        return web.Response(
            status=200,
            body=pdf,
            content_type="application/pdf",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@ocpp_routes.post("/server/phonepewheelsdrive/")
async def pay(request: web.Request):
    salt_key = "aeed1568-1a76-4fa4-9f47-3e1c81232660"
    body = await request.json()

    payload = (base64.b64encode(json.dumps(body, indent=2).encode())).decode()
    gateway = "/pg/v1/pay"
    data_for_checksum = payload + gateway + salt_key

    sha256_hash = hashlib.sha256()
    sha256_hash.update(data_for_checksum.encode())
    hash_value = sha256_hash.hexdigest()
    x_verify = hash_value + "###" + "1"

    url = "https://api-preprod.phonepe.com/apis/hermes/pg/v1/pay"
    headers = {
        "Content-Type": "application/json",
        "accept": "application/json",
        "X-VERIFY": x_verify,
    }

    res = await send_phonepe_request(url, payload, headers)
    return web.Response(
        status=200,
        body=res,
        content_type="application/json",
    )


@ocpp_routes.post("/server/phonepecallback/")
async def phonepecallback(request: web.Request):
    #     {
    #   "success": true,
    #   "code": "PAYMENT_SUCCESS",
    #   "message": "Your request has been successfully completed.",
    #   "data": {
    #     "merchantId": "FKRT",
    #     "merchantTransactionId": "MT7850590068188104",
    #     "transactionId": "T2111221437456190170379",
    #     "amount": 100,
    #     "state": "COMPLETED",
    #     "responseCode": "SUCCESS",
    #     "paymentInstrument": {
    #       "type": "UPI",
    #       "utr": "206378866112"
    #     }
    #   }
    # }

    # merchantTransactionId, phonepeTransactionId, success,
    # code, message, data, merchantId, amount
    try:
        body = await request.json()
        LOGGER.info(body)
        LOGGER.info(request.headers)
        decoded_bytes = base64.b64decode(body["response"])
        decoded_body = json.loads(decoded_bytes.decode())

        # verify SHA-256

        merchant_transaction_id = decoded_body["data"]["merchantTransactionId"]
        if decoded_body["code"] == "PAYMENT_SUCCESS":
            user_id = (
                await user_dao.get_user_id_from_merchant_transaction_id(
                    merchant_transaction_id=merchant_transaction_id
                )
            ).get("userId")
            user_details_dict = await user_dao.get_wallet_balance(user_id)
            current_balance = user_details_dict["wallet_balance"]
            new_balance = float(int(decoded_body["data"]["amount"]) / 100) + float(
                current_balance
            )

            await user_dao.update_wallet_balance(
                new_balance=new_balance,
                user_id=user_id,
            )
        await user_dao.update_phonepe_payment_status(
            success=bool(decoded_body["success"]),
            code=decoded_body["code"],
            message=decoded_body["message"],
            merchantId=decoded_body["data"]["merchantId"],
            merchantTransactionId=decoded_body["data"]["merchantTransactionId"],
            amount=int(decoded_body["data"]["amount"]),
            phonepeTransactionId=decoded_body["data"]["transactionId"],
            data=json.dumps(decoded_body["data"]),
            state=decoded_body["data"]["state"],
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


async def generate_invoice(session_id, org_id):
    organisation_info = await user_dao.get_organisation_detail(org_id=org_id)
    organisation_details = await user_dao.get_organisation_properties(org_id=org_id)
    invoice_details = await user_dao.get_session_invoice(session_id=session_id)
    if not organisation_info or not organisation_details or not invoice_details:
        raise Exception
    organisation_details["vat"] = organisation_info.get("vat")
    organisation_details["email"] = organisation_info.get("email")
    organisation_details["org_name"] = organisation_info.get("org_name")
    organisation_details["show_tax_on_invoice"] = bool(
        int(organisation_details.get("show_tax_on_invoice", "1"))
    )
    html_code = get_invoice_html(invoice_details, organisation_details)
    pdf = create_pdf(html_code)
    return pdf


async def get_necessary_session_details(session_id, start_time, tenant_id):
    try:
        meter_values = await user_dao.get_session_meter_values(
            session_id=int(session_id), tenant_id=tenant_id
        )

        if not meter_values:
            raise MissingObjectOnDB(f"meter value for session {session_id}")

        initial_meter_value = meter_values.get("initial_meter_value")
        energy_import_register = meter_values.get("energy_import_register")
        energy_import_unit = meter_values.get("energy_import_unit")
        power_import_unit = meter_values.get("power_import_unit")
        power_import_register = meter_values.get("power_import")
        soc = meter_values.get("soc")

        current_time = datetime.utcnow()
        duration = current_time - start_time
        hours = duration.total_seconds() / 3600

        if energy_import_unit == "Wh":
            if initial_meter_value <= energy_import_register:
                energy_import_register -= initial_meter_value
        elif energy_import_unit == "kWh":
            energy_import_register *= 1000
            if initial_meter_value <= energy_import_register:
                energy_import_register -= initial_meter_value
        energy_import_register /= 1000
        if power_import_unit == "W":
            power_import_register /= 1000
        initial_meter_value /= 1000

        session_paramters = await user_dao.get_session_paramters(
            session_id=session_id, tenant_id=tenant_id
        )

        if not session_paramters:
            raise MissingObjectOnDB(
                f"session paramter for session {session_id}")

        spent_duration = current_time - start_time
        hours, remainder = divmod(spent_duration.total_seconds(), 3600)
        minutes, seconds = divmod(remainder, 60)
        spent_duration_string = "{:02} hr:{:02} min".format(
            int(hours), int(minutes))
        spent_duration_without_format = "{:02}:{:02}".format(
            int(hours), int(minutes))

        return {
            session_id: {
                "session_id": int(session_id),
                "spent_minutes": spent_duration.total_seconds() / 60,
                "energy_import_register": energy_import_register,
                "spent_duration_string": spent_duration_string,
                "spent_duration_without_format": spent_duration_without_format,
                "power_import_register": power_import_register,
                "elapsed_time": "{:02}:{:02}".format(int(hours), int(minutes)),
                "soc": soc,
                "price": session_paramters.get("price"),
                "stop_charging_by": session_paramters.get("stop_charging_by"),
                "fixed_starting_fee": session_paramters.get("fixed_starting_fee", 0),
                "tenant_id": tenant_id
            }
        }
    except MissingObjectOnDB as e:
        LOGGER.error(f"{e}")
        return {session_id: {}}
    except Exception as e:
        LOGGER.error(f"{e} error at get_necessary_session_details")
        return {}


async def get_session_cost(session, tenant_id, business_mobile_app):
    try:
        cost = {"cost_with_tax": 0}
        if session:
            business_properties = await business_details_and_properties(
                tenant_id=tenant_id)

            tax_percentage = float(
                business_properties.get("tax_percentage", 5))

            if business_mobile_app:
                price_include_tax = bool(
                    int(business_properties.get("price_include_tax", 1))
                )
            else:
                enterprise_property = await get_enterprise_properties()
                price_include_tax = bool(
                    int(enterprise_property.get("price_include_tax", 1))
                )

            price = session.get("price", 0)
            fixed_starting_fee = session.get("fixed_starting_fee", 0)

            if price_include_tax:
                price = get_value_without_tax(
                    with_tax=price, tax_percent=tax_percentage)
                fixed_starting_fee = get_value_without_tax(
                    with_tax=fixed_starting_fee, tax_percent=tax_percentage)

            cost_dict = calculate_cost(
                price=price,
                tax_percent=tax_percentage,
                fixed_starting_fee=fixed_starting_fee,
                bill_by=session.get("stop_charging_by"),
                minutes=session.get("spent_minutes"),
                energy_units_kWh=session.get("energy_import_register"),
            )

            cost["cost_with_tax"] = cost_dict["final_cost"]
        session.update(cost)
        return

    except Exception as e:
        LOGGER.error(e)


@ocpp_routes.post("/server/v3/meter_values/")
async def meter_values_v3(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        current_session_id = data.get("session_id")
        current_tenant_id = data.get("tenant_id")
        current_session_cost = 0
        validate_parameters(current_session_id, current_tenant_id)

        business_mobile_app = await does_business_have_mobile_app(current_tenant_id)
        tenant_id_list = await get_tenant_ids_based_on_mobile_app(
            tenant_id=current_tenant_id,
            business_mobile_app=business_mobile_app,
        )

        is_running, id_tag, start_time = await user_dao.is_session_running_v2(
            session_id=current_session_id, tenant_id=current_tenant_id,
        )

        if not is_running:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "No session running on charger!"}),
                content_type="application/json",
            )

        user_id = await user_dao.get_user_from_id_tag(
            id_tag=id_tag, tenant_id=current_tenant_id,
            business_mobile_app=business_mobile_app
        )

        stop_task = []
        final_id_tag_dict = {}
        free_charging_energy = 45
        free_charging_minutes = 120
        should_cut_charging = False
        current_session = {}

        final_id_tag_dict = await get_rfid_of_user(
            business_mobile_app, user_id, tenant_id_list
        )
        check_object_existence(final_id_tag_dict, "Rfid card")

        result = await user_dao.get_wallet_balance(
            user_id=user_id,
            tenant_id=current_tenant_id,
            business_mobile_app=business_mobile_app,
        )
        wallet_balance = result.get("wallet_balance")

        sessions_to_stop = {}
        all_sessions = {}

        for tenant in tenant_id_list:
            id_tags = final_id_tag_dict[tenant]
            id_tags_str = "', '".join(id_tags)
            all_sessions[tenant] = {}
            tasks = []

            list_of_sessions = await user_dao.get_all_running_session_by_id_tags(
                id_tags=id_tags_str, tenant_id=tenant,
            )

            for session in list_of_sessions:
                tasks.append(
                    get_necessary_session_details(
                        session_id=session.get("id"),
                        start_time=session.get("start_time"),
                        tenant_id=tenant,
                    )
                )

            results = await asyncio.gather(*tasks) if tasks else []

            if results:
                for x in results:
                    all_sessions[tenant].update(x)

        current_session_id = int(current_session_id)
        if (all_sessions[current_tenant_id].get(current_session_id)):
            current_session = all_sessions[current_tenant_id].pop(
                current_session_id
            )

            stop_charging_by = current_session.get("stop_charging_by")
            spent_minutes = current_session.get("spent_minutes")
            elapsed_time = current_session.get("elapsed_time")
            cost = current_session.get("cost_with_tax", 0)
            soc = current_session.get("soc")
            energy_import_register = current_session.get(
                "energy_import_register", 0)

            should_cut_charging = await energy_zero_cutoff(
                session_id=current_session_id,
                stop_task=stop_task,
                id_tag=id_tag,
                user_id=user_id,
                tenant_id=current_tenant_id,
                business_mobile_app=business_mobile_app
            )

            if not should_cut_charging:
                await get_session_cost(
                    tenant_id=current_tenant_id,
                    session=current_session,
                    business_mobile_app=business_mobile_app
                )
                cost = current_session.get("cost_with_tax", 0)

                if cost == 0:
                    if stop_charging_by == "duration_in_minutes":
                        if int(spent_minutes) >= int(free_charging_minutes):
                            # await initiate_remote_stop(
                            #     session_id=session_id, id_tag=id_tag, user_id=user_id
                            # )
                            LOGGER.info(
                                "Inside time spent_minutes >= free_Charging_minutes")
                    elif stop_charging_by == "max_energy_consumption":
                        if float(energy_import_register) >= float(free_charging_energy):
                            # await initiate_remote_stop(
                            #     session_id=session_id, id_tag=id_tag, user_id=user_id
                            # )
                            LOGGER.info("Inside energy cost == 0 energy")

        overall_cost = 0

        for tenant, sessions in all_sessions.items():
            session_stop_list = []
            cost_tasks = []

            for session in sessions.values():
                session_stop_list.append(session.get("session_id"))
                cost_tasks.append(get_session_cost(
                    session=session,
                    tenant_id=tenant,
                    business_mobile_app=business_mobile_app,
                ))

            if tenant == current_tenant_id and current_session:
                sessions.update(
                    {current_session["session_id"]: current_session})
                session_stop_list.append(current_session.get("session_id"))

            sessions_to_stop[tenant] = session_stop_list
            await asyncio.gather(*cost_tasks)

            for session in sessions.values():
                overall_cost += session.get("cost_with_tax", 0)

        if overall_cost != 0 and not should_cut_charging and sessions_to_stop:
            for tenant, sessions_stop_list in sessions_to_stop.items():
                # org_minimum_balance = await user_dao.get_organisations_property(
                #     org_ids=org_id, parameter_key="minimum_wallet_balance"
                # )
                org_minimum_balance = 10
                payment_method = "wallet"
                cost = current_session.get("cost_with_tax", 0)
                if payment_method != "wallet":
                    should_cut_charging = await card_excess_cost_cutoff(
                        cost=cost,
                        id_tag=id_tag,
                        user_id=user_id,
                        stop_task=stop_task,
                        session_id=current_session_id,
                        payment_intent_id=payment_method,
                        threshold=org_minimum_balance,
                        tenant_id=tenant,
                        business_mobile_app=business_mobile_app
                    )
                else:
                    should_cut_charging = await wallet_excess_cost_cutoff(
                        id_tag=id_tag,
                        user_id=user_id,
                        stop_task=stop_task,
                        wallet_balance=wallet_balance,
                        sessions_to_stop=sessions_stop_list,
                        threshold=overall_cost + org_minimum_balance,
                        tenant_id=tenant,
                        business_mobile_app=business_mobile_app
                    )

        if should_cut_charging:
            await asyncio.gather(*stop_task) if stop_task else ""

        spent_duration_string = current_session.get(
            "spent_duration_string")
        power_import_register = current_session.get(
            "power_import_register")
        energy_import_register = current_session.get(
            "energy_import_register", 0)

        data = {
            "time_elapsed": spent_duration_string,
            "energy_transfered": str(energy_import_register),
            "power": str(power_import_register),
            "price": "{0:.2f}".format(cost),
            "soc": soc,
            "session_id": current_session_id,
            "tenant_id": current_tenant_id
        }

        await check_and_send_session_related_notification(
            user_id, current_session_id, soc, cost, elapsed_time, current_tenant_id
        )

        await send_message_to_client(
            key=user_id,
            event_name="meter_values",
            data=data,
            tenant_id=current_tenant_id,
            business_mobile_app=business_mobile_app
        )

        return web.Response(
            status=200,
            body=json.dumps(data),
            content_type="application/json",
        )

    except ParameterMissing as e:
        LOGGER.error(e)
        return e.jsonResponse

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


async def check_and_send_session_related_notification(
    user_id, session_id, soc, cost, elapsed_time, tenant_id
):
    try:
        notification_config = await firebase_dao.get_session_notification(
            session_id=session_id, tenant_id=tenant_id
        )
        if notification_config:
            notification_type = notification_config.get("notification_type")
            notification_value = notification_config.get("notification_value")
            if notification_type == "soc":
                if soc >= float(notification_value):
                    await send_firebase_notification_if_not_sent(
                        title=None,
                        user_id=user_id,
                        session_id=session_id,
                        body=None,
                        event_name="meter_values_notification_config",
                        data={
                            "action": "notification_limit_reached",
                            "sessionId": session_id,
                            "user_id": user_id,
                            "tenant_id": tenant_id,
                            "title": f"Your SoC has exceeded {soc} %",
                            "body": "click on stop charging to stop the session now!",
                        },
                        tenant_id=tenant_id
                    )
            elif notification_type == "cost":
                cost = round(float(cost), 2)
                if cost >= float(notification_value):
                    await send_firebase_notification_if_not_sent(
                        title=None,
                        body=None,
                        user_id=user_id,
                        session_id=session_id,
                        event_name="meter_values_notification_config",
                        data={
                            "action": "notification_limit_reached",
                            "sessionId": session_id,
                            "user_id": user_id,
                            "tenant_id": tenant_id,
                            "title": f"Your session cost has exceeded {notification_value}",  # noqa
                            "body": "click on stop charging to stop the session now!",
                        },
                        tenant_id=tenant_id
                    )
            elif notification_type == "duration":
                elapsed_time = datetime.strptime(elapsed_time, "%H:%M")
                elapsed_time = elapsed_time.time()
                notification_value = datetime.strptime(
                    notification_value, "%H:%M")
                notification_value = notification_value.time()
                if notification_value <= elapsed_time:
                    await send_firebase_notification_if_not_sent(
                        title=None,
                        body=None,
                        user_id=user_id,
                        session_id=session_id,
                        event_name="meter_values_notification_config",
                        data={
                            "action": "notification_limit_reached",
                            "sessionId": session_id,
                            "user_id": user_id,
                            "tenant_id": tenant_id,
                            "title": f"Your session time has exceeded {str(notification_value)}",  # noqa
                            "body": "click on stop charging to stop the session now!",
                        },
                        tenant_id=tenant_id
                    )
        return
    except Exception as e:
        LOGGER.info(e)
        return


async def energy_zero_cutoff(
    session_id, stop_task, id_tag, user_id, tenant_id, business_mobile_app
):
    should_cut_charging = False
    session_details = await user_dao.get_session_detail_by_id(session_id, tenant_id)
    if not session_details:
        return should_cut_charging
    charger_id = session_details.get("charger_id")
    connector_id = session_details.get("connector_id")
    connector_details = await user_dao.get_connector_detail(
        charger_id=charger_id, connector_id=connector_id, tenant_id=tenant_id
    )
    type = connector_details.get("type")
    if (not type) or (type != "15A"):
        return should_cut_charging
    meter_value_details = await user_dao.get_old_meter_values(
        session_id=session_id, tenant_id=tenant_id
    )
    if len(meter_value_details) == 5:
        meter_values_set = {
            float(detail.get("energy_import_register", 0))
            for detail in meter_value_details
        }
        if meter_values_set and (
            len(meter_values_set) == 1 or all(x < 0 for x in meter_values_set)
        ):
            stop_task.append(
                initiate_remote_stop(
                    session_id=session_id,
                    id_tag=id_tag,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    business_mobile_app=business_mobile_app
                )
            )
            should_cut_charging = True

    return should_cut_charging


async def card_excess_cost_cutoff(
    cost,
    id_tag,
    user_id,
    stop_task,
    session_id,
    payment_intent_id,
    threshold,
    tenant_id,
    business_mobile_app
):
    should_cut_charging = False
    payment_intent_details = await user_dao.get_payment_intent_detail(payment_intent_id)
    captured_fund = float(payment_intent_details.get("amount"))
    final_cost = cost + threshold
    if captured_fund <= final_cost:
        stop_task.append(
            initiate_remote_stop(
                session_id=session_id,
                id_tag=id_tag,
                user_id=user_id,
                tenant_id=tenant_id,
                business_mobile_app=business_mobile_app
            )
        )
        should_cut_charging = True
    LOGGER.info("Inside time captured_fund <= final_cost")
    return should_cut_charging


async def wallet_excess_cost_cutoff(
    threshold, wallet_balance, sessions_to_stop, stop_task,
    id_tag, user_id, tenant_id, business_mobile_app
):
    should_cut_charging = False
    if float(wallet_balance) <= float(threshold):
        for session in sessions_to_stop:
            stop_task.append(
                initiate_remote_stop(
                    session_id=session,
                    id_tag=id_tag,
                    user_id=user_id,
                    tenant_id=tenant_id,
                    business_mobile_app=business_mobile_app
                )
            )
            should_cut_charging = True
        string = "Inside time wallet_balance <= cost"
    else:
        string = "Inside time wallet_balance > cost"
    LOGGER.info(string)
    return should_cut_charging


# done
@ocpp_routes.post("/server/start_idle_session/")
async def start_idle_session(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        session_id = data.get("transaction_id")
        tenant_id = data.get("tenant_id")
        validate_parameters(session_id, tenant_id)
        business_mobile_app = await does_business_have_mobile_app(tenant_id)
        parameter = await user_dao.get_additional_details_from_session_parameters(
            session_id=session_id,
            tenant_id=tenant_id,
        )
        user_id = parameter["user_id"] if parameter else None
        if user_id:
            await send_message_to_client(
                key=user_id,
                event_name="idle_session_started",
                data={"session_id": session_id, "tenant_id": tenant_id},
                tenant_id=tenant_id,
                business_mobile_app=business_mobile_app
            )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "success"}),
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


# done
@ocpp_routes.post("/server/finish_idle_session/")
async def user_idle_fee(request: web.Request) -> web.Response:
    try:
        data = await request.json()
        session_id = data.get("transaction_id")
        tenant_id = data.get("tenant_id")
        validate_parameters(session_id, tenant_id)
        business_mobile_app = await does_business_have_mobile_app(tenant_id)
        invoice = await user_dao.get_invoice_by_session_id(
            session_id=session_id,
            tenant_id=tenant_id,
        )
        user_id = invoice["invoice"]["user_id"] if invoice else None
        if user_id:
            await fcm.send_notification(
                title="Invoice has been generated for your last charging session!",
                body="tap here to view.",
                user_id=user_id,
                data={
                    "action": "invoice_created",
                    "sessionId": session_id,
                    "user_id": user_id,
                },
            )
            await send_message_to_client(
                key=user_id,
                event_name="idle_session_close",
                data={"session_id": session_id, "tenant_id": tenant_id},
                tenant_id=tenant_id,
                business_mobile_app=business_mobile_app
            )
        return web.Response(
            status=200,
            body=json.dumps({"msg": "success"}),
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


@ocpp_routes.post("/server/phoneperedirect/")
async def redirect_window(request: web.Request) -> web.Response:
    try:
        data = await request.post()
        form_data = {k: v for k, v in data.items()}
        # amount = json_body['amount']
        # code = json_body['code']
        # provider_reference_id = json_body['providerReferenceId']
        # merchant_id = json_body["merchantId"]
        # transaction_id = json_body["transactionId"]
        LOGGER.info(form_data)
        if form_data["code"] == "PAYMENT_ERROR":
            html_body = """
            <html>
                <head>
                    <link href="https://fonts.googleapis.com/css?family=Nunito+Sans:400,400i,700,900&display=swap" rel="stylesheet">
                </head>
                <style>
                    body {
                        text-align: center;
                        padding: 40px 0;
                        background: #EBF0F5;
                    }
                        h1 {
                        color: #4169E1;
                        font-family: "Nunito Sans", "Helvetica Neue", sans-serif;
                        font-weight: 900;
                        font-size: 40px;
                        margin-bottom: 10px;
                        }
                        p {
                        color: #404F5E;
                        font-family: "Nunito Sans", "Helvetica Neue", sans-serif;
                        font-size:20px;
                        margin: 0;
                        }
                    #iconmark {
                        color: red;
                        font-size: 100px;
                        line-height: 200px;
                        margin-left:0px;
                    }
                    .card {
                        background: white;
                        padding: 60px;
                        border-radius: 4px;
                        box-shadow: 0 2px 3px #C8D0D8;
                        display: inline-block;
                        margin: 0 auto;
                    }
                </style>
                <body>
                    <div class="card">
                        <div style="border-radius:200px; height:200px; width:200px; background: #F8FAF5; margin:0 auto;">
                            <p id="iconmark">!</p>
                        </div>
                        <h1>Failed</h1>
                        <p>Payment Failed, Unfortunately Payment Failed, Please try again. You can safely close this window by pressing 'x' on top left.</p>
                    </div>
                </body>
            </html>
            """  # noqa
            return web.Response(status=200, body=html_body, content_type="text/html")
        if form_data["code"] == "PAYMENT_PENDING":
            await user_dao.update_phonepe_payment_status(
                success=False,
                amount=form_data["amount"],
                code="PAYMENT_PENDING",
                data={},
                merchantId=form_data["merchantId"],
                merchantTransactionId=form_data["transactionId"],
                message="",
                phonepeTransactionId=form_data["providerReferenceId"],
                state="PENDING",
            )
            html_body = """
            <html>
                <head>
                    <link href="https://fonts.googleapis.com/css?family=Nunito+Sans:400,400i,700,900&display=swap" rel="stylesheet">
                </head>
                <style>
                    body {
                        text-align: center;
                        padding: 40px 0;
                        background: #EBF0F5;
                    }
                        h1 {
                        color: #4169E1;
                        font-family: "Nunito Sans", "Helvetica Neue", sans-serif;
                        font-weight: 900;
                        font-size: 40px;
                        margin-bottom: 10px;
                        }
                        p {
                        color: #404F5E;
                        font-family: "Nunito Sans", "Helvetica Neue", sans-serif;
                        font-size:20px;
                        margin: 0;
                        }
                    #iconmark {
                        color: red;
                        font-size: 100px;
                        line-height: 200px;
                        margin-left:0px;
                    }
                    .card {
                        background: white;
                        padding: 60px;
                        border-radius: 4px;
                        box-shadow: 0 2px 3px #C8D0D8;
                        display: inline-block;
                        margin: 0 auto;
                    }
                </style>
                <body>
                    <div class="card">
                        <div style="border-radius:200px; height:200px; width:200px; background: #F8FAF5; margin:0 auto;">
                            <p id="iconmark">!</p>
                        </div>
                        <h1>Pending</h1>
                        <p>Payment Pending, We will update the status shortly. You can safely close this window by pressing 'x' on top left.</p>
                    </div>
                </body>
            </html>
            """  # noqa
            return web.Response(status=200, body=html_body, content_type="text/html")

        html_body = """
        <html>
            <head>
                <link href="https://fonts.googleapis.com/css?family=Nunito+Sans:400,400i,700,900&display=swap" rel="stylesheet">
            </head>
            <style>
                body {
                    text-align: center;
                    padding: 40px 0;
                    background: #EBF0F5;
                }
                    h1 {
                    color: #88B04B;
                    font-family: "Nunito Sans", "Helvetica Neue", sans-serif;
                    font-weight: 900;
                    font-size: 40px;
                    margin-bottom: 10px;
                    }
                    p {
                    color: #404F5E;
                    font-family: "Nunito Sans", "Helvetica Neue", sans-serif;
                    font-size:20px;
                    margin: 0;
                    }
                i {
                    color: #9ABC66;
                    font-size: 100px;
                    line-height: 200px;
                    margin-left:-15px;
                }
                .card {
                    background: white;
                    padding: 60px;
                    border-radius: 4px;
                    box-shadow: 0 2px 3px #C8D0D8;
                    display: inline-block;
                    margin: 0 auto;
                }
            </style>
            <body>
                <div class="card">
                    <div style="border-radius:200px; height:200px; width:200px; background: #F8FAF5; margin:0 auto;">
                        <i class="checkmark">✓</i>
                    </div>
                <h1>Success</h1>
                <p>Payment succcessful. You can safely close this window by pressing 'x' on top left.</p>
                </div>
            </body>
        </html>
        """  # noqa
        return web.Response(status=200, body=html_body, content_type="text/html")

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@ocpp_routes.post("/server/payzone/callback/")
async def payzone_callback(request: web.Request) -> web.Response:
    try:
        raw_content = await request.content.read()
        callback_body = json.loads(
            raw_content) if raw_content is not None else ""

        status = callback_body.get("status")
        merchantPaymentId = callback_body.get(
            "id")
        paymentGatewayPaymentId = callback_body.get(
            "internalId"
        )
        paymentType = callback_body.get("paymentType")
        paymentMethod = callback_body.get("paymentMethod")
        data = callback_body.get("transactions")
        amount = callback_body.get("lineItem").get("amount")
        tenant_id = callback_body.get(
            "properties").get("tenant_id")

        await user_dao.update_payzone_transaction(
            status=status,
            merchantPaymentId=merchantPaymentId,
            paymentGatewayPaymentId=paymentGatewayPaymentId,
            paymentType=paymentType,
            paymentMethod=paymentMethod,
            data=json.dumps(data),
            tenant_id=tenant_id
        )

        if (status == "CHARGED" or status == "CHARGEBACK_REVERSED"):
            user_id = await user_dao.get_user_id_for_payzone_transaction(merchantPaymentId, tenant_id)
            current_wallet_balance = await user_dao.get_wallet_balance(
                user_id=user_id,
                tenant_id=tenant_id,
                business_mobile_app=True if tenant_id != 'enterprise' else False
            )
            new_wallet_balance = float(current_wallet_balance.get(
                "wallet_balance"))+float(amount)
            await user_dao.update_wallet_balance(
                new_balance=new_wallet_balance,
                user_id=user_id, tenant_id=tenant_id,
                business_mobile_app=True if tenant_id != 'enterprise' else False
            )

        if (status == "CHARGED_BACK"):
            user_id = await user_dao.get_user_id_for_payzone_transaction(merchantPaymentId, tenant_id)
            current_wallet_balance = await user_dao.get_wallet_balance(
                user_id=user_id,
                tenant_id=tenant_id,
                business_mobile_app=True if tenant_id != 'enterprise' else False
            )
            new_wallet_balance = float(current_wallet_balance.get(
                "wallet_balance"))-float(amount)
            await user_dao.update_wallet_balance(
                new_balance=new_wallet_balance,
                user_id=user_id, tenant_id=tenant_id,
                business_mobile_app=True if tenant_id != 'enterprise' else False
            )

        return web.Response(status=200, body=json.dumps({"data": ""}), content_type="application/json")
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )
