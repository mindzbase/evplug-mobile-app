from dao import user_dao
import logging
from errors.mysql_error import ParameterMissing, MissingObjectOnDB
from mail import send_plain_invoice_email
import utils

LOGGER = logging.getLogger("server")


async def consume_and_create_invoice(session_id, tenant_id):
    try:
        utils.validate_parameters(session_id, tenant_id)
        invoice = None
        session_parameter_details = await user_dao.get_session_related_parameters(
            session_id=session_id, tenant_id=tenant_id
        )
        if not session_parameter_details:
            raise MissingObjectOnDB("Session Parameter")
        utils.check_object_existence()
        # payment_method_details = await user_dao.get_payment_intent_id(
        #     session_id=session_id
        # )
        # payment_method = (
        #     "wallet"
        #     if not payment_method_details
        #     else payment_method_details.get("payment_intent_id")
        # )
        payment_method = "wallet"
        invoice = await create_invoice(
            session_id=session_id,
            session_parameter_details=session_parameter_details,
            payment_method=payment_method,
            tenant_id=tenant_id,
        )
        if not invoice:
            MissingObjectOnDB("Session Parameter/Duration")
        idle_fee = 0
        idle_after = 0
        price_id = invoice.get("price_id", None)
        user_id = invoice.get("user_id", None)
        cost_with_tax = invoice.get("charging_cost_with_tax", 0)
        gateway_fee = invoice.get("gateway_fee")
        if price_id:
            price_details = await user_dao.get_price_details_by_price_id(
                price_id=price_id, tenant_id=tenant_id
            )
            idle_fee = price_details.get("idle_charging_fee", 0)
            idle_after = price_details.get("apply_after", 0)
        if not (idle_fee and idle_after):
            if payment_method != "wallet":
                payment_intent_details = await user_dao.get_payment_intent_detail(
                    payment_method
                )
                captured_fund = float(payment_intent_details.get("amount"))
                final_amount = (
                    captured_fund
                    if captured_fund < cost_with_tax
                    else (cost_with_tax + gateway_fee)
                )
            else:
                final_amount = cost_with_tax
            await utils.deduct_fund_by_payment_method(
                user_id=user_id,
                payment_method=payment_method,
                final_amount=final_amount,
                tenant_id=tenant_id,
            )
        return
    except MissingObjectOnDB as e:
        LOGGER.error(e)
    except ParameterMissing as e:
        LOGGER.error(e)
    except Exception as e:
        LOGGER.error(e)


async def get_additional_details_from_session_parameters(
    session_id,
    total_energy_used,
    elapsed_time,
    price_include_tax,
    tax_percent,
    tenant_id,
):
    try:
        additional_details_sp = (
            await user_dao.get_additional_details_from_session_parameters(
                session_id=session_id, tenant_id=tenant_id
            )
        )
        details = {}
        if additional_details_sp:
            stop_charging_by = additional_details_sp.get("stop_charging_by")
            price = additional_details_sp.get("price")
            vehicle_id = additional_details_sp.get("vehicle_id")
            user_id = additional_details_sp.get("user_id")
            price_id = additional_details_sp.get("price_id")
            bill_by_string = (
                "By Unit (kWh)"
                if stop_charging_by == "max_energy_consumption"
                else "By Time (Hour)"
            )
            if stop_charging_by == "max_energy_consumption":
                cost = total_energy_used * price
            elif stop_charging_by == "duration_in_minutes":
                cost = (elapsed_time * price) / 60
            if price_include_tax:
                cost_with_tax = cost
                cost, tax = utils.calculate_base_and_tax(
                    total_amount=cost_with_tax, tax_percentage=tax_percent
                )
            else:
                tax, cost_with_tax = utils.calculate_tax_and_total(
                    base_amount=cost, tax_percentage=tax_percent
                )
            details["bill_by_string"] = bill_by_string
            details["price"] = price
            details["price_id"] = price_id
            details["cost"] = cost
            details["cost_with_tax"] = cost_with_tax
            details["user_id"] = user_id
            details["vehicle_id"] = vehicle_id
        return None if not details else details
    except Exception as e:
        LOGGER.error(e)


async def get_additional_details_from_session_duration(
    session_id,
    total_energy_used,
    elapsed_time,
    price_include_tax,
    tax_percent,
):
    try:
        additional_details_sd = (
            await user_dao.get_additional_details_from_session_duration(
                session_id=session_id
            )
        )
        price_id = None
        details = {}
        if additional_details_sd:
            stop_charging_by = additional_details_sd.get("stop_charging_by")
            price = additional_details_sd.get("price")
            vehicle_id = additional_details_sd.get("vehicle_id")
            user_id = additional_details_sd.get("user_id")
            price_id = additional_details_sd.get("price_id")
            bill_by_string = (
                "By Unit (kWh)" if stop_charging_by == "amount" else "By Time (Hour)"
            )
            if stop_charging_by == "amount":
                cost = total_energy_used * price
            elif stop_charging_by == "end_time":
                cost = (elapsed_time / 60) * price / 60
            if price_include_tax:
                cost_with_tax = cost
                cost, tax = utils.calculate_base_and_tax(
                    total_amount=cost_with_tax, tax_percentage=tax_percent
                )
            else:
                tax, cost_with_tax = utils.calculate_tax_and_total(
                    base_amount=cost, tax_percentage=tax_percent
                )
            details["bill_by_string"] = bill_by_string
            details["price"] = price
            details["price_id"] = price_id
            details["cost"] = cost
            details["cost_with_tax"] = cost_with_tax
            details["user_id"] = user_id
            details["vehicle_id"] = vehicle_id
        return None if not details else details
    except Exception as e:
        LOGGER.error(e)


async def sent_invoice_via_email(org_id, session_id, user_id):
    try:
        organisation_info = await user_dao.get_organisation_detail(org_id=org_id)
        invoice_details = await user_dao.get_session_invoice(session_id=session_id)
        organisation_details = await user_dao.get_organisation_properties(org_id=org_id)
        if (
            (not organisation_info)
            or (not organisation_details)
            or (not invoice_details)
        ):
            raise Exception(
                "Organisation Details or Organisation Info or Invoice Details is empty"
            )
        organisation_details["vat"] = organisation_info.get("vat")
        organisation_details["email"] = organisation_info.get("email")
        organisation_details["org_name"] = organisation_info.get("org_name")
        organisation_details["org_id"] = org_id
        res = await user_dao.get_user_details(user_id=user_id)
        receiver_email = res.get("email")
        await send_plain_invoice_email(
            invoice_details=invoice_details,
            org_details=organisation_details,
            receiver_email=receiver_email,
        )
    except Exception as e:
        LOGGER.error(e)


async def get_gateway_fee(org_id, organisation_details):
    has_mobile_app = organisation_details.get("has_mobile_app")
    gateway_fee = 0
    if has_mobile_app:
        gateway_fee = organisation_details.get("gateway_fee", 0)
    else:
        org_details = await user_dao.get_parent_org_id(org_id)
        parent_org_id = org_details.get("parent_org_id") if org_details else None
        organisation_details = await user_dao.get_organisation_properties(
            org_id=parent_org_id
        )
        gateway_fee = organisation_details.get("gateway_fee", 0)
    return gateway_fee


async def create_invoice(
    session_id, session_parameter_details, payment_method, tenant_id
):
    try:
        charger_id = session_parameter_details.get("charger_id")
        connector_id = session_parameter_details.get("connector_id")
        connector_type = session_parameter_details.get("connector_type")
        connector_max_output = session_parameter_details.get("max_output")
        charger_type = session_parameter_details.get("charger_type")
        location_name = session_parameter_details.get("location_name")
        location_id = session_parameter_details.get("location_id")
        elapsed_time = session_parameter_details.get("elapsed_time")
        session_start_time = session_parameter_details.get("session_start_time")
        total_energy_used = (
            float(session_parameter_details.get("final_meter_value"))
            - float(session_parameter_details.get("initial_meter_value"))
        ) / 1000
        organisation_details = await user_dao.get_organisation_properties(
            tenant_id=tenant_id
        )
        currency = organisation_details.get("currency", "")
        # price_include_tax = bool(
        #     int(organisation_details.get("price_include_tax", 1))
        # )
        # gateway_fee = await get_gateway_fee(
        #     org_id=org_id, organisation_details=organisation_details
        # )
        # gateway_fee = float(gateway_fee) if payment_method != "wallet" else 0
        gateway_fee = 0
        price_include_tax = 1
        tax_percent = (
            float(organisation_details["tax_percentage"])
            if organisation_details.get("tax_percentage")
            else 0
        )
        tax_percent = 5
        additional_details = await get_additional_details_from_session_parameters(
            session_id=session_id,
            total_energy_used=total_energy_used,
            elapsed_time=elapsed_time,
            price_include_tax=price_include_tax,
            tax_percent=tax_percent,
            tenant_id=tenant_id,
        )
        if not additional_details:
            raise MissingObjectOnDB("Session Parameter/Duration")
        price = additional_details.get("price")
        bill_by_string = additional_details.get("bill_by_string")
        price_id = additional_details.get("price_id")
        cost = round(additional_details.get("cost"), 2)
        cost_with_tax = round(additional_details.get("cost_with_tax"), 2)
        user_id = additional_details.get("user_id")
        vehicle_id = additional_details.get("vehicle_id")

        invoice_id = await user_dao.insert_invoice(
            charger_id=charger_id,
            charger_type=charger_type,
            connector_id=connector_id,
            connector_type=connector_type,
            connector_maxoutput=connector_max_output,
            location_id=location_id,
            location_name=location_name,
            session_id=session_id,
            session_start_time=session_start_time,
            session_runtime=elapsed_time,
            session_energy_used=total_energy_used,
            bill_by=bill_by_string,
            price=price,
            currency=currency,
            charging_cost=round(cost, 2),
            tax_percentage=tax_percent,
            charging_cost_with_tax=round(cost_with_tax, 2),
            user_id=user_id,
            vehicle_id=vehicle_id,
            gateway_fee=gateway_fee,
            tenant_id=tenant_id,
            charging_plan_id=price_id,
        )
        invoice = {
            "invoice_id": invoice_id,
            "charger_id": charger_id,
            "connector_id": connector_id,
            "connector_type": connector_type,
            "connector_max_output": f"{connector_max_output}KW",
            "charger_type": charger_type,
            "location": location_name,
            "session_id": session_id,
            "elapsed_time": str(elapsed_time),
            "total_energy_used": f"{total_energy_used:.2f}",
            "bill_by": bill_by_string,
            "price": price,
            "price_id": price_id,
            "charging_cost": cost,
            "currency": currency,
            "tax_percent": tax_percent,
            "charging_cost_with_tax": cost_with_tax,
            "gateway_fee": gateway_fee,
            "user_id": user_id,
            "vehicle_id": vehicle_id,
        }
        return invoice
    except MissingObjectOnDB as e:
        LOGGER.error(e)
    except Exception as e:
        LOGGER.error(e)
