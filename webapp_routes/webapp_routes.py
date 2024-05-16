import json
import asyncio
import logging
import random
import string
from typing import Any, Dict
from uuid import uuid4
from aiohttp import web
import stripe
from dao import user_dao
from routes.ocpp_routes import (
    card_excess_cost_cutoff,
    energy_zero_cutoff,
    get_necessary_session_details,
    get_session_cost,
)
import ocpp_server
from utils import validate_parameters
from webapp_routes.dao import (
    add_rfid_user,
    create_webapp_user,
    get_connector_details,
    get_session_id,
    get_web_app_user,
)
from errors.mysql_error import MissingObjectOnDB, ParameterMissing, PaymentMethodInvalid
from config import config
from webapp_routes.service_layer import set_vehicle, verify_user_id


LOGGER = logging.getLogger("server")
webapp_routes = web.RouteTableDef()


@webapp_routes.get("/webapp/charger/{charger_id}/connector/{connector_id}/")
async def charger_connector_status(request: web.Request) -> web.Response:
    try:
        charger_id = request.match_info.get("charger_id")
        connector_id = request.match_info.get("connector_id")
        validate_parameters(charger_id, connector_id)
        res = await get_connector_details(
            charger_id=charger_id, connector_id=connector_id
        )
        if not res:
            raise MissingObjectOnDB(object="Charger/Connector/Price")
        org_id = res.get("org_id")
        orgs_properties = await user_dao.get_organisation_properties(org_id=org_id)
        res.update(
            {
                "tax_percentage": orgs_properties.get("tax_percentage"),
                "currency": orgs_properties.get("currency"),
                "price_include_tax": bool(
                    int(orgs_properties.get("price_include_tax", 0))
                ),
            }
        )
        return web.Response(
            status=200,
            body=json.dumps(res),
            content_type="application/json",
        )

    except ParameterMissing as e:
        return e.jsonResponse

    except MissingObjectOnDB as e:
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@webapp_routes.post("/webapp/prepare_stripe/")
async def prepare_stripe2(request: web.Request) -> web.Response:
    try:
        data = request.json()
        data: Dict[str, Any] = await request.json()
        amount = data.get("amount")
        validate_parameters(amount)
        stripe.api_key = config["STRIPE_API_KEY"]
        payment_intent = stripe.PaymentIntent.create(
            amount=int(float(amount) * 100),
            currency="inr",
        )
        return web.Response(
            status=200,
            body=json.dumps(
                {
                    "client_secret": f"{payment_intent.get('client_secret', None)}",
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
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@webapp_routes.post("/webapp/signup/")
async def signup(request: web.Request):
    try:
        org_id = request.headers["organisationId"]
        data: Dict[str, Any] = await request.json()
        email = data.get("email")
        validate_parameters(email)

        user = await get_web_app_user(email=email)
        user_id = user.get("user_id", None)

        if not user_id:
            user_id = str(uuid4())
            id_tag = "".join(random.choices(string.ascii_letters, k=7))
            await create_webapp_user(user_id=user_id, email=email, org_id=org_id)
            await add_rfid_user(id_tag=id_tag, user_id=user_id, org_id=org_id)
            response_msg = "User added successfully!"
        else:
            response_msg = "User already exists."

        return web.Response(
            status=200,
            body=json.dumps({"user_id": user_id, "msg": response_msg}),
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


@webapp_routes.post("/webapp/set_vehicle/")
async def setup_vehicle(request: web.Request) -> web.Response:
    try:
        data: Dict[str, Any] = await request.json()
        user_id = data.get("user_id")
        validate_parameters(user_id)
        await verify_user_id(user_id)
        response = await set_vehicle(user_id)
        return web.Response(
            status=200,
            body=json.dumps(response),
            content_type="application/json",
        )
    except ParameterMissing as e:
        return e.jsonResponse

    except MissingObjectOnDB as e:
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@webapp_routes.post("/webapp/save_captured_card/")
async def save_captured_card(request: web.Request) -> web.Response:
    try:
        request.headers["organisationId"]
        data: Dict[str, Any] = await request.json()
        user_id = data.get("user_id")
        payment_intent_id = data.get("payment_intent_id")
        payment_method_id = data.get("payment_method_id")
        currency = data.get("currency")
        charger_id = data.get("charger_id")
        connector_id = data.get("connector_id")
        amount = data.get("amount")
        validate_parameters(
            user_id,
            payment_intent_id,
            payment_method_id,
            currency,
            charger_id,
            connector_id,
            amount,
        )
        cust_id = payment_intent_id
        await verify_user_id(user_id)
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
        # await user_dao.insert_stripe_customer(user_id, cust_id)
        return web.Response(
            status=200,
            body=json.dumps(
                {
                    "msg": "Mandate Details are saved successfully.",
                }
            ),
            content_type="application/json",
        )

    except ParameterMissing as e:
        return e.jsonResponse

    except MissingObjectOnDB as e:
        return e.jsonResponse

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
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@webapp_routes.get("/webapp/connector_status/")
async def connector_status(request: web.Request) -> web.Response:
    try:
        charger_id = request.query["charger_id"]
        connector_id = request.query["connector_id"]
        validate_parameters(charger_id, connector_id)
        connector_status = await user_dao.get_specified_connector_status(
            charger_id, connector_id
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
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@webapp_routes.post("/webapp/start_charging/")
async def start_charging(request: web.Request) -> web.Response:
    try:
        data: Dict[str, Any] = await request.json()
        user_id = data.get("user_id", None)
        charger_id = data.get("charger_id", None)
        connector_id = data.get("connector_id", None)
        validate_parameters(user_id, charger_id, connector_id)
        await verify_user_id(user_id)
        id_tag = await user_dao.get_users_id_tag(user_id)
        # existing_session = await user_dao.get_current_running_session_id_with_id_tag(
        #     id_tag=id_tag
        # )
        # if existing_session:
        #     is_session_started = False
        #     msg = f"""
        #         User have Existing session running with session_id {existing_session}.
        #     """
        # else:
        #     is_session_started, msg = await ocpp_server.remote_start(
        #         charger_id=charger_id,
        #         id_tag=id_tag,
        #         connector_id=connector_id,
        #     )
        is_session_started, msg = await ocpp_server.remote_start(
            charger_id=charger_id,
            id_tag=id_tag,
            connector_id=connector_id,
        )

        if is_session_started:
            return web.Response(
                status=200,
                body=json.dumps({"msg": "Charging started Successfully"}),
                content_type="application/json",
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
    except ParameterMissing as e:
        return e.jsonResponse

    except MissingObjectOnDB as e:
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@webapp_routes.get("/webapp/get_session/")
async def get_session(request: web.Request) -> web.Response:
    try:
        charger_id = request.query["charger_id"]
        connector_id = request.query["connector_id"]
        user_id = request.query["user_id"]
        validate_parameters(charger_id, connector_id, user_id)
        id_tag = await user_dao.get_users_id_tag(user_id)
        if not id_tag:
            raise MissingObjectOnDB("IdTag of user")
        session_id = await get_session_id(charger_id, connector_id, id_tag)
        if not session_id:
            raise MissingObjectOnDB("session_id")
        return web.Response(
            status=200,
            body=json.dumps({"msg": "Success", "session_id": session_id}),
            content_type="application/json",
        )

    except ParameterMissing as e:
        return e.jsonResponse

    except MissingObjectOnDB as e:
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@webapp_routes.get("/webapp/meter_values/{session_id}/")
async def meter_values(request: web.Request) -> web.Response:
    try:
        session_id = request.match_info.get("session_id")
        validate_parameters(session_id)
        is_running, id_tag, start_time = await user_dao.is_session_running_v2(
            session_id=session_id
        )
        if not is_running:
            return web.Response(
                status=200,
                body=json.dumps(
                    {"screen": "invoice", "msg": "No session running on charger!"}
                ),
                content_type="application/json",
            )

        user_id, org_id = await user_dao.get_user_from_id_tag(id_tag=id_tag)
        session_details = await get_necessary_session_details(
            session_id=session_id,
            start_time=start_time,
        )
        cost = 0
        free_charging_minutes = 120
        free_charging_energy = 45
        stop_task = []
        should_cut_charging = False
        session = session_details.get(session_id)
        await get_session_cost(session=session)
        cost = session.get("cost_with_tax", 0)
        stop_charging_by = session.get("stop_charging_by")
        spent_minutes = session.get("spent_minutes")
        energy_import_register = session.get("energy_import_register")
        spent_duration_string = session.get("spent_duration_without_format")
        power_import_register = session.get("power_import_register")
        cost = session.get("cost_with_tax", 0)
        soc = session.get("soc")
        should_cut_charging = await energy_zero_cutoff(
            session_id=session_id, stop_task=stop_task, id_tag=id_tag, user_id=user_id
        )
        if cost != 0:
            org_minimum_balance = await user_dao.get_organisations_property(
                org_ids=org_id, parameter_key="minimum_wallet_balance"
            )
            payment_method_details = await user_dao.get_payment_intent_id(
                session_id=session_id
            )
            payment_method = (
                "wallet"
                if not payment_method_details
                else payment_method_details.get("payment_intent_id")
            )
            if payment_method != "wallet":
                should_cut_charging = await card_excess_cost_cutoff(
                    cost=cost,
                    id_tag=id_tag,
                    user_id=user_id,
                    stop_task=stop_task,
                    session_id=session_id,
                    payment_intent_id=payment_method,
                    threshold=float(org_minimum_balance.get(org_id, 0)),
                )
        elif cost == 0:
            if stop_charging_by == "duration_in_minutes":
                if spent_minutes >= free_charging_minutes:
                    # await initiate_remote_stop(
                    #     session_id=session_id, id_tag=id_tag, user_id=user_id
                    # )
                    LOGGER.info("Inside time spent_minutes >= free_Charging_minutes")
            elif stop_charging_by == "max_energy_consumption":
                if energy_import_register >= free_charging_energy:
                    # await initiate_remote_stop(
                    #     session_id=session_id, id_tag=id_tag, user_id=user_id
                    # )
                    LOGGER.info("Inside energy cost == 0 energy")
        if should_cut_charging:
            await asyncio.gather(*stop_task) if stop_task else ""

        data = {
            "screen": "metervalue",
            "time_elapsed": spent_duration_string,
            "session_started_at": str(start_time),
            "energy_transfered": str(energy_import_register),
            "power": str(power_import_register),
            "price": "{0:.2f}".format(cost),
            "soc": soc,
            "session_id": session_id,
        }
        return web.Response(
            status=200,
            body=json.dumps(data),
            content_type="application/json",
        )

    except ParameterMissing as e:
        return e.jsonResponse

    except MissingObjectOnDB as e:
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@webapp_routes.post("/webapp/stop_charging/")
async def stop_public_charging(request: web.Request) -> web.Response:
    try:
        data: Dict[str, Any] = await request.json()
        user_id = data.get("user_id", None)
        session_id = data.get("session_id", None)
        validate_parameters(user_id, session_id)
        await verify_user_id(user_id)
        id_tag = await user_dao.get_users_id_tag(user_id)
        (is_stopped, msg) = await ocpp_server.remote_stop(session_id, id_tag)
        LOGGER.info(f"is_stopped: {is_stopped}")
        LOGGER.info(f"msg: {msg}")
        res = {"is_stopped": is_stopped, "msg": msg}
        if res["is_stopped"]:
            return web.Response(
                status=200,
                body=json.dumps(res),
                content_type="application/json",
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
    except ParameterMissing as e:
        return e.jsonResponse

    except MissingObjectOnDB as e:
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@webapp_routes.get("/webapp/get_invoice/{session_id}/")
async def get_invoice(request: web.Request):
    try:
        session_id = int(request.match_info["session_id"])
        if session_id is None or session_id == "" or session_id <= 0:
            return web.Response(
                status=400,
                body=json.dumps({"msg": "Invalid Parameters"}),
                content_type="application/json",
            )
        invoice = await user_dao.get_invoice_by_session_id(session_id=session_id)
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
            body=json.dumps({"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )
