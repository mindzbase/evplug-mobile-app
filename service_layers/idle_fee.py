import math
from dao import user_dao
from datetime import datetime, timedelta
from dao.app_dao import does_business_have_mobile_app
from service_layers.FN_layer import send_firebase_notification_if_not_sent


async def get_idle_details(session_id, user_id, tenant_id):
    data = {}

    session_paramter_info = await user_dao.get_price_plan_by_session_parameter(
        session_id=session_id,
        tenant_id=tenant_id,
    )

    vehicle_id = session_paramter_info.get("vehicle_id")
    charger_id = session_paramter_info.get("charger_id")
    connector_id = session_paramter_info.get("connector_id")
    price_id = session_paramter_info.get("charging_plan_id")

    business_mobile_app = await does_business_have_mobile_app(tenant_id)

    vehicle_details = await user_dao.get_vehicle_details(
        vehicle_id=vehicle_id,
        tenant_id=tenant_id,
        business_mobile_app=business_mobile_app,
    )

    if vehicle_details:
        vehicle_details["created_at"] = str(vehicle_details["created_at"])
        vehicle_details["updated_at"] = str(vehicle_details["updated_at"])
        data["vehicle"] = vehicle_details

    charging_station_details = await user_dao.get_location_charger_details(
        charger_id=charger_id,
        connector_id=connector_id,
        tenant_id=tenant_id,
    )

    if charging_station_details:
        data["location_name"] = charging_station_details.get("label")
        data["location_address"] = charging_station_details.get(
            "address_line_1")
        data["charger_id"] = charging_station_details.get("charger_id")
        data["charger_name"] = charging_station_details.get("charger_name")
        data["connector_id"] = charging_station_details.get("connector_id")
        data["connector_type"] = charging_station_details.get("type")

    res = await user_dao.get_pricing_plan(
        price_id=price_id,
        tenant_id=tenant_id,
    )

    apply_after_minutes = res.get("apply_after")
    idle_charging_fee = float(res.get("idle_charging_fee"))
    fixed_starting_fee = float(res.get("fixed_starting_fee"))

    session_detail = await user_dao.get_session_detail(
        session_id=session_id,
        tenant_id=tenant_id,
    )

    session_stop_time = session_detail.get("stop_time")
    change_status_time = datetime.utcnow()

    if isinstance(session_stop_time, str):
        session_stop_time = datetime.strptime(
            session_stop_time, "%Y-%m-%dT%H:%M:%S")

    interval_of_status_change = change_status_time - session_stop_time
    cost_of_idle_vehicle = 0

    if not apply_after_minutes and not idle_charging_fee:
        data["remaining_time"] = "00:00:00"
        data["apply_after"] = apply_after_minutes
        data["idle_charging_fee"] = idle_charging_fee
        data["fixed_starting_fee"] = fixed_starting_fee
    elif interval_of_status_change > timedelta(minutes=apply_after_minutes):
        interval_of_status_change_in_seconds = interval_of_status_change.total_seconds()
        interval_of_status_change_in_minutes = math.ceil(
            interval_of_status_change_in_seconds / 60
        )
        over_time = interval_of_status_change_in_minutes - apply_after_minutes
        cost_of_idle_vehicle = over_time * idle_charging_fee
        data["elapsed_time"] = str(timedelta(minutes=over_time))
        data["cost_of_idle_vehicle"] = cost_of_idle_vehicle

        await send_firebase_notification_if_not_sent(
            title="Free Idle Time exceeded.",
            body=f"Idle fee penalty for session {session_id} is started.",
            user_id=user_id,
            session_id=session_id,
            tenant_id=tenant_id,
            event_name="idle_fee_started",
            data={
                "action": "Idle fee penalty.",
                "sessionId": session_id,
                "user_id": user_id,
            },
        )
    else:
        data["remaining_time"] = str(
            timedelta(minutes=apply_after_minutes) - interval_of_status_change
        ).split(".")[0]
        data["apply_after"] = apply_after_minutes
        data["idle_charging_fee"] = idle_charging_fee

    return {tenant_id: {session_id: data}}
