from datetime import datetime
import math
import passlib.hash
import stripe
from errors.mysql_error import MissingObjectOnDB, ParameterMissing
from errors.mysql_error import ValidateInstance
from errors.mysql_error import MissingInfoException
import ocpp_server
from dao import user_dao
import logging
from websocket import send_message_to_client
from mail import send_plain_invoice_email


LOGGER = logging.getLogger("server")


def encrypt_password(password):
    return passlib.hash.sha256_crypt.encrypt(password, rounds=1000)


def check_password(password, password_hash):
    return passlib.hash.sha256_crypt.verify(password, password_hash)


def calculate_base_and_tax(total_amount, tax_percentage):
    base_amount = total_amount / (1 + tax_percentage / 100)
    tax_amount = total_amount - base_amount
    return round(base_amount, 2), round(tax_amount, 2)


def calculate_tax_and_total(base_amount, tax_percentage):
    tax_amount = (base_amount * tax_percentage) / 100
    total_amount = base_amount + tax_amount
    return round(tax_amount, 2), round(total_amount, 2)


class By_hour:
    class duration:
        def get_amount(duration_in_minutes, price_in_hour):
            return (price_in_hour / 60) * duration_in_minutes

        def get_units_consumed(duration_in_minutes, max_output):
            return (max_output / 60) * duration_in_minutes

    class amount:
        def get_units_consumed(amount, max_output, price):
            units = (max_output / price) * amount
            durations = (60 / price) * amount
            return units, durations


class By_unit:
    class duration:
        def get_units_consumed(duration_in_minutes, max_output):
            return (max_output / 60) * duration_in_minutes

        def get_amount(units, price_in_units):
            return price_in_units * units

    class amount:
        def get_amount(paid_amount, tax):
            tax_amount = (tax / 100) * paid_amount
            return paid_amount - tax_amount, tax_amount

        def get_units_consumed(amount, max_output, price_in_units):
            units = (1 / price_in_units) * amount
            durations = (60 / max_output) * units
            return units, durations


def get_soc_added(vehicle_battery, units_consumed):
    return min((units_consumed / vehicle_battery) * 100, 100.0)


def get_range_added(range, soc_added):
    return (soc_added * range) / 100


def calculate_tax_amount(paid_amount, tax):
    tax_amount = (tax / 100) * paid_amount
    return paid_amount + tax_amount, tax_amount


async def stop_charging(
    user_id, id_tag, charger_id, connector_id, session_id, vehicle_id
):
    (is_stopped, msg) = await ocpp_server.remote_stop(session_id, id_tag)
    LOGGER.info(f"is_stopped: {is_stopped}")
    LOGGER.info(f"msg: {msg}")
    res = {"is_stopped": is_stopped, "msg": msg}
    if is_stopped:
        data = await user_dao.get_session_details(session_id, charger_id, connector_id)
        if data:
            data.update({"is_charging_stopped": is_stopped})
            charging_cost = data["invoice"]["charging_cost"]
            tax_percent = data["invoice"]["tax_percent"]
            charging_cost_with_tax = data["invoice"]["charging_cost_with_tax"]
            id = await user_dao.insert_public_charging_session_details(
                user_id,
                vehicle_id,
                charger_id,
                connector_id,
                session_id,
                charging_cost,
                tax_percent,
                charging_cost_with_tax,
            )
            data["invoice"]["invoice_id"] = id
            amount_added = charging_cost_with_tax * -1
            user_details_dict = await user_dao.get_wallet_balance(user_id)

            current_balance = user_details_dict["wallet_balance"]
            new_balance = float(amount_added) + float(current_balance)

            await user_dao.update_wallet_balance(
                new_balance=new_balance,
                user_id=user_id,
            )
            res.update({"data": data})
            return res
    return res


# async def idle_charging_info(
#     session_id, session_start_time, change_status_time, user_id
# ):
#     try:
#         price_plan_info = await user_dao.get_price_plan_by_session_parameter(
#             session_id=session_id
#         )
#         if not price_plan_info:
#             raise MissingInfoException(
#                 message=f"""
#                     Either Price Plan or Session Parameter not found for session id: {
#                         session_id
#                     }
#                 """
#             )
#         apply_after_minutes = price_plan_info.get("apply_after")
#         idle_charging_fee = price_plan_info.get("idle_charging_fee", 0)
#         if isinstance(change_status_time, str):
#             change_status_time = datetime.strptime(
#                 change_status_time, "%Y-%m-%dT%H:%M:%S"
#             )
#         if isinstance(session_start_time, str):
#             session_start_time = datetime.strptime(
#                 session_start_time, "%Y-%m-%dT%H:%M:%S"
#             )
#         interval_of_status_change = change_status_time - session_start_time
#         interval_of_status_change_in_seconds = interval_of_status_change.total_seconds()
#         interval_of_status_change_in_minutes = math.ceil(
#             interval_of_status_change_in_seconds / 60
#         )

#         cost_of_idle_vehicle = 0
#         if interval_of_status_change_in_minutes > apply_after_minutes:
#             cost_of_idle_vehicle = (
#                 interval_of_status_change_in_minutes * idle_charging_fee
#             )

#             res = await user_dao.get_wallet_balance(user_id=user_id)
#             wallet_balance = res.get("wallet_balance") if res else None
#             if wallet_balance is None:
#                 raise MissingInfoException(
#                     f"Unable to fetch wallet balance for user_id: {user_id}"
#                 )
#             wallet_balance = wallet_balance - cost_of_idle_vehicle
#             await user_dao.update_wallet_balance(
#                 new_balance=wallet_balance, user_id=user_id
#             )
#         else:
#             LOGGER.info(
#                 f"""
#                 Skipped Idle charging processing because
#                 interval time {interval_of_status_change_in_minutes} is <= than
#                 free idle charging time which is {apply_after_minutes}
#             """
#             )
#         return
#     except MissingInfoException as e:
#         LOGGER.error(e)
#     except Exception as e:
#         LOGGER.error(e)


async def idle_charging_info_and_send_invoice(
    session_id, session_stop_time, change_status_time
):
    try:
        price_plan_info = await user_dao.get_price_plan_by_session_parameter(
            session_id=session_id
        )
        if not price_plan_info:
            raise MissingInfoException(
                message=f"""
                    Either Price Plan or Session Parameter not found for session id: {
                        session_id
                    }
                """
            )
        apply_after_minutes = int(price_plan_info.get("apply_after", 0))
        idle_charging_fee = price_plan_info.get("idle_charging_fee", 0)
        user_id = await user_dao.get_user_id_by_session_id(session_id=session_id)
        LOGGER.info(
            f"""{session_id} : get_user_id_by_session_id : {user_id}""")
        if isinstance(change_status_time, str):
            change_status_time = datetime.strptime(
                change_status_time, "%Y-%m-%dT%H:%M:%S.%f"
            )
        if isinstance(session_stop_time, str):
            session_stop_time = datetime.strptime(
                session_stop_time, "%Y-%m-%dT%H:%M:%S"
            )
        interval_of_status_change = change_status_time - session_stop_time
        interval_of_status_change_in_seconds = interval_of_status_change.total_seconds()
        interval_of_status_change_in_minutes = math.ceil(
            interval_of_status_change_in_seconds / 60
        )
        cost_of_idle_vehicle = 0
        extra_time = interval_of_status_change_in_minutes - apply_after_minutes
        if extra_time > 0:
            cost_of_idle_vehicle = extra_time * idle_charging_fee
        else:
            LOGGER.info(
                f"""
                Skipped Idle charging processing because
                interval time {interval_of_status_change_in_minutes} is <= than
                free idle charging time which is {apply_after_minutes}
            """
            )
        await user_dao.insert_idle_fee(
            session_id=session_id,
            idle_minutes=extra_time,
            idle_price=idle_charging_fee,
            idle_charging_cost=cost_of_idle_vehicle,
        )
        user_details = await user_dao.get_user_details(user_id=user_id)
        org_id = user_details.get("org_id")
        receiver_email = user_details.get("email")
        organisation_info = await user_dao.get_organisation_detail(org_id=org_id)
        invoice_details = await user_dao.get_session_invoice(session_id=session_id)
        organisation_details = await user_dao.get_organisation_properties(org_id=org_id)
        if (
            (not organisation_info)
            or (not organisation_details)
            or (not invoice_details)
        ):
            raise MissingInfoException(
                "Organisation Details or Organisation Info or Invoice Details is empty"
            )
        organisation_details["vat"] = organisation_info.get("vat")
        organisation_details["email"] = organisation_info.get("email")
        organisation_details["org_name"] = organisation_info.get("org_name")
        organisation_details["org_id"] = org_id
        organisation_details["show_tax_on_invoice"] = bool(
            int(organisation_details.get("show_tax_on_invoice", "1"))
        )
        if idle_charging_fee and apply_after_minutes:
            final_amount = round(
                (
                    invoice_details.get("charging_cost_with_tax")
                    + invoice_details.get("gateway_fee", 0)
                    + invoice_details.get("idle_charging_cost", 0)
                ),
                2,
            )
            payment_method_details = await user_dao.get_payment_intent_id(
                session_id=session_id,
            )
            payment_method = (
                "wallet"
                if not payment_method_details
                else payment_method_details.get("payment_intent_id")
            )
            if payment_method != "wallet":
                payment_intent_details = await user_dao.get_payment_intent_detail(
                    payment_method,
                )
                captured_fund = float(payment_intent_details.get("amount"))
                final_amount = (
                    captured_fund if captured_fund < final_amount else final_amount
                )
            await deduct_fund_by_payment_method(
                user_id=user_id,
                payment_method=payment_method,
                final_amount=final_amount,
                allow_nagative_balance=True,
            )

        await send_plain_invoice_email(
            invoice_details=invoice_details,
            org_details=organisation_details,
            receiver_email=receiver_email,
        )
        invoice = await user_dao.get_invoice_by_session_id(session_id=session_id)

        # refund_response = await initiate_stripe_refund(
        #     amount=(captured_fund-final_amount) * 100,
        #     charger_id=invoice_details.get("charger_id"),
        #     connector_id=invoice_details.get("connector_id"),
        #     user_id=user_id,
        #     reason="requested_by_customer"
        # )
        # if refund_response.status == "succeeded":
        #     LOGGER.info({"msg": "Refund initiated successfully!"}),

        # else:
        #     LOGGER.info({"msg": "Refund failed",
        #                 "status": refund_response.status})

        return invoice
    except MissingInfoException as e:
        LOGGER.error(e)
    except Exception as e:
        LOGGER.error(e)


def cost_calculator(entity, price, tax_percent):
    cost = entity * price
    cost_with_tax = round(cost + (cost * (tax_percent / 100)), 2)
    cost = round(cost, 2)
    return cost, cost_with_tax


def time_converter(elapsed_time):
    min, sec = divmod(elapsed_time, 60)
    hour, min = divmod(min, 60)
    return "%02d:%02d:%02d" % (hour, min, sec)


def create_pdf(data):
    from utils import LOGGER

    try:
        import pdfkit

        options = {
            # "page-size": "Letter",
            "page-size": "A4",
            "margin-top": "0.25in",
            "margin-right": "0.25in",
            "margin-bottom": "0.25in",
            "margin-left": "0.25in",
        }
        return pdfkit.from_string(data, None, options=options)
    except Exception as e:
        LOGGER.error(e)


def format_time_with_leading_zeros(td):
    total_seconds = int(td.total_seconds())
    hours = total_seconds // 3600
    minutes = (total_seconds // 60) % 60
    seconds = total_seconds % 60
    formatted_string = f"{hours:02}:{minutes:02}:{seconds:02}"
    return formatted_string


async def deduct_fund_by_payment_method(
    user_id, payment_method, final_amount, tenant_id, allow_nagative_balance=False
):
    LOGGER.info(payment_method)
    if not payment_method:
        return
    if payment_method == "wallet":
        LOGGER.info("capturing funds from wallet")
        user_details_dict = await user_dao.get_wallet_balance(user_id, tenant_id)
        current_balance = user_details_dict["wallet_balance"]
        new_balance = float(current_balance) - round(final_amount, 2)

        if allow_nagative_balance:
            if new_balance < 0:
                new_balance = 0

        await user_dao.update_wallet_balance(
            new_balance=new_balance, user_id=user_id, tenant_id=tenant_id
        )
    else:
        # Note: stripe key is set in one of the previous api
        #       calls because it is a global object

        fund_capture_intent = stripe.PaymentIntent.capture(
            payment_method, amount_to_capture=int(float(final_amount) * 100)
        )
        LOGGER.info("capturing funds from card")
        LOGGER.info(fund_capture_intent)
        await user_dao.insert_stripe_transaction_info(
            payment_intent_id=fund_capture_intent.charges.data[0].payment_intent,
            max_amount=fund_capture_intent.charges.data[0].amount,
            amount_captured=fund_capture_intent.charges.data[0].amount_captured,
            amount_refunded=fund_capture_intent.charges.data[0].amount_refunded,
            txn_charge_id=fund_capture_intent.charges.data[0].balance_transaction,
            currency=fund_capture_intent.charges.data[0].currency,
            cust_id=fund_capture_intent.charges.data[0].customer,
            receipt_url=fund_capture_intent.charges.data[0].receipt_url,
            status=fund_capture_intent.charges.data[0].status,
        )

    return


def validate_parameters(*args, instances=[]):
    for arg in args:
        if not arg or arg == "undefined":
            raise ParameterMissing()
        elif arg and instances:
            instance_type = instances[args.index(arg)]
            result = isinstance(arg, instance_type)
            if not result:
                raise ValidateInstance(variable=arg, type=instance_type)


async def initiate_stripe_refund(amount, charger_id, connector_id, user_id, reason):
    # Note: stripe key is set in one of the previous api
    # calls because it is a global object

    res = await user_dao.get_latest_payment_intent_id(charger_id, connector_id, user_id)
    payment_intent_id = res.get("payment_intent_id", None)
    if payment_intent_id:
        refund_response = stripe.Refund.create(
            amount=amount * 100, payment_intent=payment_intent_id, reason=reason
        )
        return refund_response
    return {"status": "Payment Intent not found!"}


def check_object_existence(obj, obj_name):
    if not obj:
        raise MissingObjectOnDB(obj_name)


def get_currency_symbol(curr):
    currency = {
        "dollar": "$",
        "rupee": "₹",
        "pound": "£",
        "dirham": "د.إ",
        "moroccan dirham": "MAD"
    }
    return currency.get(curr, "$")
