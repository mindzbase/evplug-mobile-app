import asyncio
import logging
import uuid
from datetime import date, datetime, time
from typing import Any
from dao.app_dao import business_details_and_properties, does_business_have_mobile_app, get_tenants_properties

import utils
from dao import helperdao
from enums.repeat_interval import RepeatInterval
from enums.span import Span
from errors.mysql_error import MissingObjectOnDB, MySQLError

LOGGER = logging.getLogger("server")


async def validate_token(user_id: str, business_mobile_app: bool, tenant_id: str):
    try:
        table = (
            f"`tenant{tenant_id}`.`customer_invites`"
            if business_mobile_app
            else "`customer_invites`"
        )
        query = f"""
            SELECT user_id from {table} WHERE user_id = '{user_id}'
        """
        res = await helperdao.fetchone(query)
        if res is not None:
            return res[0]
        return None
    except MySQLError as e:
        raise MySQLError(str(e))


async def get_user_from_id_tag(id_tag: str, tenant_id: str, business_mobile_app: bool):
    try:
        query_for_enterprise = f"""
            SELECT user_id from rfid_cards WHERE rfid_number = '{id_tag}'
        """

        query_for_tenant = f"""
            SELECT user_id from `tenant{tenant_id}`.`rfid_cards`
            WHERE rfid_number = '{id_tag}'
        """

        if not business_mobile_app:
            res = await helperdao.fetchone_dict(query_for_enterprise)
            if res:
                return res.get("user_id")

        res = await helperdao.fetchone_dict(query_for_tenant)
        return res.get("user_id") if res else {}
    except Exception as e:
        raise MySQLError(str(e))


async def check_user_vehicle_exist(vehicle_id, user_id, tenant_id, business_mobile_app):
    try:
        table = (
            f"`tenant{tenant_id}`.`user_vehicles`"
            if business_mobile_app
            else '`user_vehicles`'
        )
        query = f"""
            SELECT
                id
            FROM
                {table}
            WHERE
                vehicle_id = '{vehicle_id}'
            AND user_id='{user_id}'
        """
        res = await helperdao.fetchone(query)
        if res is not None:
            return res[0]
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_user_details_with_user_id(
    tenant_id: str,
    business_mobile_app: bool,
    user_id: str = None,
    fid: str = None,
):
    table = (
        f"""
            `tenant{tenant_id}`.`customer_invites` u
        LEFT JOIN `tenant{tenant_id}`.`users` ud ON
            u.user_id=ud.id
        LEFT JOIN `tenant{tenant_id}`.`user_vehicles` uv ON
            u.user_id = uv.user_id
        LEFT JOIN `tenant{tenant_id}`.`vehicles` v ON
    """
        if business_mobile_app
        else """
            `customer_invites` u
        LEFT JOIN `users` ud ON
            u.user_id=ud.id
        LEFT JOIN `user_vehicles` uv ON
            u.user_id = uv.user_id
        LEFT JOIN `vehicles` v ON
    """
    )
    query = f"""
        SELECT
            u.user_id AS user_id,
            u.email,
            u.phone,
            v.id as vehicle_id,
            v.manufacturer,
            v.model,
            v.battery_size,
            u.wallet_balance,
            u.name,
            u.address,
            u.token,
            uv.id,
            uv.is_default,
            v.image_url,
            CASE
                WHEN ud.email_verified_at IS NOT NULL THEN 1
                WHEN ud.email_verified_at IS NULL THEN 0
            END AS is_email_verified
        FROM
            {table}
            uv.vehicle_id = v.id
        WHERE
    """

    if user_id is not None:
        query += f'u.user_id = "{user_id}";'

    if fid is not None:
        query += f'u.firebase_uid = "{fid}";'

    if user_id is None and fid is None:
        return None

    res = await helperdao.fetchall_dict(query)
    vehicles = []
    vehicles_dict = {}
    location_sets = set()
    user_id = ""
    name = ""
    email = ""
    is_email_verified = False
    phone = ""
    wallet_balance = ""
    address = ""
    favorite_charging_stations = []
    if res:
        for row in res:
            if row.get('vehicle_id') is not None:
                if row.get('id') in vehicles_dict:
                    pass
                else:
                    vehicles_dict.update(
                        {
                            row.get('id'): {
                                "id": row.get('vehicle_id'),
                                "unique_id": row.get('id'),
                                "manufacturer": str(row.get('manufacturer', "")),
                                "model": str(row.get("model")),
                                "battery_size": float(row.get("battery_size")),
                                "is_default": bool(row.get("is_default")),
                                "image_url": str(row.get("image_url")),
                            },
                        },
                    )
            if row.get("location_id") is not None:
                location_sets.add(row.get("location_id"))
            user_id = row.get("user_id")
            name = row.get("name")
            email = row.get("email")
            phone = row.get("phone")
            token = row.get("token")
            wallet_balance = float(row.get("wallet_balance"))
            address = row.get("address")
            is_email_verified = bool(row.get("is_email_verified", 0))
        for val in location_sets:
            favorite_charging_stations.append(val)

        for value in vehicles_dict.values():
            vehicles.append(value)
        return {
            "user_id": user_id,
            "name": name,
            "email": email,
            "is_email_verified": is_email_verified,
            "phone": phone,
            "token": token,
            "wallet_balance": wallet_balance,
            "address": address,
            "vehicles": vehicles,
            "favorite_charging_stations": favorite_charging_stations,
        }
    return None


async def get_user_id_from_fid(fid: str):
    query = f"""
        select u.user_id as user_id from user_details u where
        firebase_uid ='{fid}'
    """
    res: list = await helperdao.fetchone(query)
    if res is not None:
        return res[0]
    return None


async def get_wallet_balance(
    user_id: str, tenant_id: str, business_mobile_app: bool = False
):
    user_table = (
        f"`tenant{tenant_id}`.`customer_invites`"
        if business_mobile_app
        else "`customer_invites`"
    )
    query = f"""
        SELECT
            user_id,
            wallet_balance
        FROM
            {user_table}
        WHERE
            user_id='{user_id}'
    """
    res: list = await helperdao.fetchone_dict(query)
    return {} if not res else res


async def is_session_running(session_id: str, tenant_id: str):
    query = f"""
        SELECT
            id,
            start_time
        FROM
            `tenant{tenant_id}`.`sessions`
        WHERE
            id={session_id}
        AND is_running=1;
    """
    res = await helperdao.fetchone(query)
    if res is not None:
        return True, res[1]
    return False, None


async def get_session_duration_and_charger_details(session_id):
    query = f"""
        SELECT
            cs.stop_charging_by,
            pp.billing_type,
            pp.price,
            cs.end_time AS end_time,
            cs.amount AS paid_amount
        FROM
            sessions s
        INNER JOIN session_duration cs ON
            cs.session_id = s.id
        INNER JOIN chargers c ON
            s.charger_id = c.charger_id
        INNER JOIN price_plans pp ON
            pp.price_id = c.price_id
        WHERE
            s.id = {session_id};
    """
    res = await helperdao.fetchone(query)
    if res is not None:
        return res
    return None


async def get_session_paramters(session_id, tenant_id):
    query = f"""
        SELECT
            cs.stop_charging_by,
            cs.billing_type,
            cs.price,
            cs.fixed_starting_fee,
            cs.duration_in_minutes AS end_time,
            cs.max_energy_consumption AS total_energy,
            s.start_id_tag
        FROM
            `tenant{tenant_id}`.`sessions` s
        INNER JOIN
            `tenant{tenant_id}`.`session_parameters` cs
        ON
            s.id = cs.session_id
        INNER JOIN
            `tenant{tenant_id}`.`chargers` c
        ON
            c.charger_id = s.charger_id
        INNER JOIN
            `tenant{tenant_id}`.`locations` l
        ON
            c.location_id = l.id
        WHERE
            s.id = {session_id}
    """
    res = await helperdao.fetchone_dict(query)
    return res


# this one for invoice details
async def get_invoice_by_user_and_session_id(user_id: str, session_id: str, tenant_id: str):
    query = f"""
        SELECT
            l.label as name,
            c.charger_id,
            pp.billing_type,
            pp.price,
            cc.max_output,
            cc.type,
            cc.connector_id,
            s.final_meter_value,
            s.initial_meter_value,
            TIMESTAMPDIFF(
                SECOND,
                s.start_time,
                s.stop_time
            ) as elapsed_time,
            psd.id AS invoice_id,
            psd.charging_cost,
            psd.id,
            psd.charging_cost_with_tax
        FROM
            `tenant{tenant_id}`.`sessions` s
        INNER JOIN `tenant{tenant_id}`.`chargers` c ON
            c.charger_id = s.charger_id
        INNER JOIN `tenant{tenant_id}`.`connectors` cc ON
            cc.charger_id = c.charger_id
        INNER JOIN `tenant{tenant_id}`.`charging_plans` pp ON
            pp.id = cc.charging_plan_id
        INNER JOIN `tenant{tenant_id}`.`locations` l ON
            l.id = c.location_id
        INNER JOIN `tenant{tenant_id}`.`business_transactions` psd ON
            psd.session_id = s.id
        WHERE
            s.id = "{session_id}" AND psd.user_id="{user_id}";
    """
    res = await helperdao.fetchone_dict(query)
    if res is None:
        await asyncio.sleep(4)
        LOGGER.info("ideally wait for 2 seconds")
        res = await helperdao.fetchone(query)
        LOGGER.info(f"called res again {res}")
    if res is not None:
        LOGGER.info(res)
        elapsed_time = utils.time_converter(res.get('elapsed_time'))
        organisation_properties = await business_details_and_properties(tenant_id)
        price = float(res.get("price"))
        data = {
            "invoice": {
                "id": res.get('id'),
                "charger_id": res.get("charger_id"),
                "connector": {
                    "id": res.get("connector_id"),
                    "type": res.get("type"),
                    "max_output": f"{res.get('max_output')}KW",
                },
                "location": res.get('name'),
                "bill_by": res.get('billing_type'),
                "price": price,
                "session": {
                    "session_id": session_id,
                    "elapsed_time": str(elapsed_time),
                    "total_energy_used": float(
                        (
                            res.get('final_meter_value') -
                            res.get('initial_meter_value')
                        ) / 1000
                    ),
                },
                "charging_cost": res.get('charging_cost'),
                "currency": organisation_properties.get('currency'),
                "charging_cost_with_tax": res.get('charging_cost_with_tax'),
            }
        }
        return data
    return None


async def update_wallet_balance(new_balance: float, user_id: str, tenant_id: str, business_mobile_app: bool):
    table = (
        f"`tenant{tenant_id}`.`customer_invites`"
        if business_mobile_app
        else "`customer_invites`"
    )
    query = f"""
        UPDATE
            {table}
        SET
            wallet_balance = {new_balance}
        WHERE
            user_id='{user_id}'
    """
    await helperdao.upsert_delete(query)
    return None


async def add_favorite_stations(user_id, location_id, tenant_id):
    query = f"""
        INSERT INTO
            `tenant{tenant_id}`.`favorite_charging_stations` (`user_id`, `location_id`)
        VALUES
            ('{user_id}', '{location_id}')
    """
    await helperdao.upsert_delete(query)
    return


async def remove_favorite_stations(user_id, location_id, tenant_id):
    query = f"""
        DELETE FROM
            `tenant{tenant_id}`.`favorite_charging_stations`
        WHERE
            user_id='{user_id}'
        AND location_id='{location_id}';
    """
    await helperdao.upsert_delete(query)
    return


async def get_favorite_stations(user_id: str, day: str, tenant_id: str):
    query = f"""
        SELECT
            l.id,
            l.label,
            l.address_line_1 as address1,
            l.geo_coordinates,
            la.is_active,
            la.start_time,
            la.end_time
        FROM
            `tenant{tenant_id}`.`favorite_charging_stations` fcs
        INNER JOIN
            `tenant{tenant_id}`.`locations` l
        ON
            fcs.location_id=l.id
        INNER JOIN
            `tenant{tenant_id}`.`locations_hours` la
        ON
            l.id=la.location_id
        WHERE
            fcs.user_id='{user_id}'
        AND la.day='{day}';
    """
    locations = await helperdao.fetchall_dict(query)
    if locations is not None:
        stations = {}
        for location in locations:
            station = {}
            station["id"] = location.get("id")
            station["name"] = location.get("name")
            station["address1"] = location.get("address1")
            station["geo_coordinates"] = location.get("geo_coordinates")
            station["is_active"] = location.get("is_active")
            station["timings"] = (
                f"{location.get('from_time')} - {location.get('to_time')}"
            )
            # remove this line after update
            station["time"] = f"{location.get('from_time')} - {location.get('to_time')}"
            station["is_fav"] = True
            station["day"] = day
            station["from_time"] = utils.format_time_with_leading_zeros(
                location.get("from_time")
            )
            station["to_time"] = utils.format_time_with_leading_zeros(
                location.get("to_time")
            )
            stations[location.get("id")] = station
        return stations
    return None


async def get_all_vehicles(business_mobile_app, tenant_id):
    table = (
        "`vehicles`" if not business_mobile_app else f"`tenant{tenant_id}`.`vehicles`"
    )
    query = f"""
        SELECT v.id, v.manufacturer, v.model, v.battery_size, v.image_url
        from {table} v;
    """
    vehicles = await helperdao.fetchall(query)
    if vehicles is not None:
        vehicles_list = []
        for vehicle in vehicles:
            ride = {}
            ride["id"] = vehicle[0]
            ride["manufacturer"] = vehicle[1]
            ride["model"] = vehicle[2]
            ride["battery_size"] = vehicle[3]
            ride["image_url"] = vehicle[4]
            vehicles_list.append(ride)
        return {"vehicles": vehicles_list}
    return None


async def get_all_vehiclesv2(business_mobile_app, tenant_id):
    table = (
        "`vehicles`" if not business_mobile_app else f"`tenant{tenant_id}`.`vehicles`"
    )
    query = f"""
        SELECT v.id, v.manufacturer, v.model, v.battery_size, v.image_url
        from {table} v;
    """
    vehicles = await helperdao.fetchall(query)
    rides = {}
    if vehicles is not None:
        for vehicle in vehicles:
            ride = {}
            ride["id"] = vehicle[0]
            ride["manufacturer"] = vehicle[1]
            ride["model"] = vehicle[2]
            ride["battery_size"] = vehicle[3]
            ride["image_url"] = vehicle[4]
            if rides.get(vehicle[1]) is not None:
                rides[vehicle[1]].append(ride)
            else:
                rides[vehicle[1]] = []
                rides[vehicle[1]].append(ride)
        vehicleList = []
        for key in rides:
            vehicleList.append(rides[key])
        return {"vehicles": vehicleList}
    return None


async def add_users_vehicle(user_id, vehicle_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`user_vehicles`"
        if business_mobile_app
        else "`user_vehicles`"
    )
    query = f"""
        INSERT INTO {table} (`user_id`, `vehicle_id`)
        VALUES ('{user_id}', '{vehicle_id}')
    """
    id = await helperdao.upsert_delete(query)
    return id


async def set_default_vehicle(user_id, vehicle_id, business_mobile_app, tenant_id):
    table = (
        "`user_vehicles`"
        if not business_mobile_app
        else f"`tenant{tenant_id}`.`user_vehicles`"
    )
    query = f"""
        UPDATE
            {table}
        SET
            `is_default` = 0
        WHERE
            `user_id` = '{user_id}';
        UPDATE
            {table}
        SET
            `is_default` = 1
        WHERE
            `user_id` = '{user_id}' AND `vehicle_id` = '{vehicle_id}';
    """
    await helperdao.upsert_delete(query)
    return


async def insert_default_vehicle(user_id, vehicle_id, business_mobile_app, tenant_id):
    table = (
        "`user_vehicles`"
        if not business_mobile_app
        else f"`tenant{tenant_id}`.`user_vehicles`"
    )
    query = f"""
        UPDATE
            {table}
        SET
            `is_default` = 0
        WHERE
            `user_id` = '{user_id}';
        INSERT INTO {table}(
            `user_id`,
            `vehicle_id`,
            `is_default`,
            `created_at`
        )
        VALUES(
            '{user_id}',
            '{vehicle_id}',
            1,
            '{datetime.utcnow()}'
        )
    """
    await helperdao.upsert_delete(query)
    return


async def get_user_vehicle(user_id, vehicle_id, business_mobile_app, tenant_id):
    table = (
        "`user_vehicles`"
        if not business_mobile_app
        else f"`tenant{tenant_id}`.`user_vehicles`"
    )
    query = f"""
        SELECT *
        FROM
            {table}
        WHERE
            `user_id` = '{user_id}' AND `vehicle_id` = '{vehicle_id}'
    """
    res = await helperdao.fetchall_dict(query)
    return res


async def remove_users_vehicle(vehicle_id, user_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`user_vehicles`"
        if business_mobile_app
        else '`user_vehicles`'
    )
    query = f"""
        DELETE FROM
            {table}
        WHERE
            vehicle_id='{vehicle_id}'
        AND user_id='{user_id}';
    """
    await helperdao.upsert_delete(query)
    return


async def get_current_running_session_id(
    charger_id: str, connector_id: str, id_tag: str, tenant_id: str
):
    try:
        query = f"""
            SELECT
                id,
                start_time
            FROM
                `tenant{tenant_id}`.`sessions`
            WHERE
                charger_id = '{charger_id}'
            AND connector_id='{connector_id}'
            AND start_id_tag='{id_tag}'
            AND is_running = 1
            ORDER BY
                start_time
            DESC;
        """
        time_start = time.time()
        timeout = 0
        res = await helperdao.fetchone(query)
        while res is None and timeout < 40:
            await asyncio.sleep(2)
            LOGGER.info("ideally wait for 2 seconds")
            res = await helperdao.fetchone(query)
            LOGGER.info("called res again")
            timeout = time.time() - time_start
        if res is not None:
            return res[0], res[1]
        return None, None
    except Exception as e:
        raise MySQLError(str(e))


async def get_session_details(session_id, charger_id, connector_id):
    query = f"""
        SELECT
            l.label as name,
            c.charger_id,
            pp.billing_type,
            pp.price,
            cc.max_output,
            cc.type,
            cc.connector_id,
            s.final_meter_value,
            s.initial_meter_value,
            IFNULL(
                TIMESTAMPDIFF(
                    MINUTE,
                    s.start_time,
                    sd.end_time
                ),
                0
            ),
            IFNULL(
                TIMESTAMPDIFF(
                    SECOND,
                    s.start_time,
                    s.stop_time
                ),
                0
            ),
            sd.duration_in_minutes,
            sd.amount,
            pp.org_id
        FROM
            sessions s
        INNER JOIN chargers c ON
            c.charger_id = s.charger_id
        INNER JOIN price_plans pp on
            pp.price_id=c.price_id
        INNER JOIN charger_connector_details cc ON
            cc.charger_id = c.charger_id
        INNER JOIN locations l ON
            l.id = c.location_id
        INNER JOIN session_duration sd ON
            sd.session_id = s.id
        WHERE
            s.id = {session_id}
        AND cc.connector_id = {connector_id}
        AND c.charger_id = '{charger_id}';
    """
    res = await helperdao.fetchone(query)
    time_start = time.time()
    timeout = 0
    while res[8] is None and timeout < 40:
        await asyncio.sleep(2)
        LOGGER.info("ideally wait for 2 seconds")
        res = await helperdao.fetchone(query)
        LOGGER.info(f"called res again {res}")
        timeout = time.time() - time_start
    if res is not None:
        LOGGER.info(res)

        elapsed_time = utils.time_converter(res[11])
        org_id = res[14]
        organisation_properties = await get_organisation_properties(org_id=org_id)
        price_include_tax = bool(
            int(organisation_properties.get("price_include_tax", 0))
        )
        price = res[3]
        entity = (
            res[12] / 60) if res[2] == "per_hour" else (res[8] - res[9]) / 1000
        tax_percent = float(organisation_properties.get("tax_percentage", 5))
        if res[13] and res[13] != -1:
            if price_include_tax:
                cost_with_tax = res[13]
            else:
                cost = res[13]
                tax, cost_with_tax = utils.calculate_tax_and_total(
                    base_amount=cost, tax_percentage=tax_percent
                )
        elif res[12] and res[12] != -1:
            cost = entity * price
            tax, cost_with_tax = utils.calculate_tax_and_total(
                base_amount=cost, tax_percentage=tax_percent
            )
        else:
            cost = 0
            cost_with_tax = 0
        currency = "AED"
        data = {
            "invoice": {
                "charger_id": res[1],
                "connector": {
                    "id": res[7],
                    "type": res[6],
                    "max_output": f"{res[5]}KW",
                },
                "charger_type": res[4],
                "location": res[0],
                "bill_by": res[2],
                "price": price,
                "session": {
                    "session_id": session_id,
                    "elapsed_time": str(elapsed_time),
                    "total_energy_used": float((res[8] - res[9]) / 1000),
                    "soc": "0",
                },
                "charging_cost": round(cost, 2),
                "currency": currency,
                "tax_percent": tax_percent,
                "charging_cost_with_tax": round(cost_with_tax, 2),
            }
        }
        return data
    return None


async def insert_public_charging_session_details(
    user_id,
    vehicle_id,
    charger_id,
    connector_id,
    session_id,
    charging_cost,
    tax_percent,
    charging_cost_with_tax,
):
    query = f"""
        INSERT INTO `public_session_details` (`session_id`, `charger_id`,
        `connector_id`, `vehicle_id`, `user_id`, `charging_cost`,
        `tax_percent`, `charging_cost_with_tax`) VALUES ('{session_id}', '{charger_id}',
        {connector_id}, {vehicle_id}, '{user_id}', {charging_cost},
        {tax_percent}, '{charging_cost_with_tax}')
    """
    id = await helperdao.upsert_delete(query)
    return id


# ---------------------------------code below are extra---------------------------------
async def create_and_add_charging_schedule(
    user_id: str,
    title: str,
    charger_id: str,
    start_time: datetime,
    stop_time_duration: datetime,
    repeat_interval: RepeatInterval,
    one_time_date: date,
    days: str,
    is_custom_repeated: bool,
):
    try:
        if is_custom_repeated is None:
            is_custom_repeated = "NULL"
        charging_schedule_query = f"""
            INSERT into home_charging_schedule(title, start_time, stop_time_duration,
            repeat_interval, one_time_date, days, is_custom_repeated) VALUES (
            '{title}', '{start_time}', '{stop_time_duration}', '{repeat_interval}',
            NULLIF('{one_time_date}', 'None'), "{days}", {is_custom_repeated})
        """
        user_charging_schedule_query = """
            INSERT into user_home_charging_schedule(user_id, charger_id,
            charging_schedule_id, is_enabled) VALUES ('{}', '{}', {}, {})
        """
        charging_schedule_id = await helperdao.upsert_delete(charging_schedule_query)
        await helperdao.upsert_delete(
            user_charging_schedule_query.format(
                user_id, charger_id, charging_schedule_id, True
            )
        )
        return charging_schedule_id
    except Exception as e:
        raise MySQLError(str(e))


async def delete_user_charging_schedule(user_id: uuid, charging_schedule_id: int):
    try:
        query = f"""
            UPDATE user_home_charging_schedule SET is_enabled=0 WHERE
            user_id = '{user_id}' AND charging_schedule_id = {charging_schedule_id}
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def get_user_charging_schedules(user_id: uuid):
    try:
        query = f"""
            SELECT cs.id, cs.title, cs.start_time, cs.stop_time_duration,
            cs.repeat_interval, cs.one_time_date, cs.days, cs.is_custom_repeated
            from user_home_charging_schedule u
            INNER JOIN home_charging_schedule cs ON cs.id = u.charging_schedule_id
            WHERE u.user_id = '{user_id}' AND u.is_enabled = 1
        """
        res = await helperdao.fetchall(query)
        res_list = []
        if res is not None:
            for row in res:
                res_list.append(
                    {
                        "charging_schedule_id": row[0],
                        "title": row[1],
                        "start_time": str(row[2]),
                        "stop_time_duration": str(row[3]),
                        "repeat_interval": row[4],
                        "one_time_date": str(row[5]),
                        "custom_days": row[6],
                        "is_custom_repeated": row[7],
                    }
                )
        return res_list
    except Exception as e:
        raise MySQLError(str(e))


async def get_charging_session_history(user_id: uuid):
    try:
        query = f"""
            SELECT s.start_time, s.stop_time, s.initial_meter_value,
            s.final_meter_value, s.charger_id, hcs.title
            FROM home_charging_sessions cs
            INNER JOIN sessions s ON s.id = cs.session_id
            LEFT JOIN home_charging_schedule hcs ON hcs.id = cs.charging_schedule_id
            WHERE user_id = '{user_id}'
        """
        res = await helperdao.fetchall(query)
        res_list = []
        if res is not None:
            for row in res:
                res_list.append(
                    {
                        "start_time": str(row[0]),
                        "stop_time_duration": str(row[1]),
                        "initial_meter_value": row[2],
                        "final_meter_value": int(row[3] / 1000),
                        "charger_id": row[4],
                        "title": row[5] if (row[5] is not None) else "User initiated",
                        "date": str(row[0].date()),
                    }
                )
        return res_list
    except Exception as e:
        raise MySQLError(str(e))


# TODO discuss with both enterprise and buessiness can both have apps
async def get_users_id_tag(user_id: str, tenant_id: str, business_mobile_app: bool) -> Any:
    try:
        query_for_enterprise = f"""
            SELECT
                rfid_number
            FROM
                rfid_cards
            WHERE user_id = '{user_id}'
        """
        query_for_tenant = f"""
            SELECT
                rfid_number
            FROM
                `tenant{tenant_id}`.rfid_cards
            WHERE user_id = '{user_id}'
        """
        if not business_mobile_app:
            res = await helperdao.fetchone(query_for_enterprise)
            if res is not None:
                return res[0]

        res = await helperdao.fetchone(query_for_tenant)
        if res is not None:
            return res[0]
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_all_users_id_tag(user_id: str) -> Any:
    try:
        query = f"""
            SELECT id_tag from rfid_cards WHERE user_id = '{user_id}'
        """
        res = await helperdao.fetchall_dict(query)
        id_tags_list = []
        if res is not None:
            for r in res:
                id_tags_list.append(r["id_tag"])
        return id_tags_list
    except Exception as e:
        raise MySQLError(str(e))


async def get_session_id(charger_id: str):
    try:
        query = f"""
            SELECT id from sessions WHERE charger_id = '{charger_id}'
            ORDER BY created_at DESC
        """
        res = await helperdao.fetchone(query)
        if res is not None:
            return res[0]
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def insert_new_charging_session(
    user_id: str, charging_schedule_id: int, charger_id: str
):
    try:
        query = """
            INSERT into home_charging_sessions(user_id,
            charging_schedule_id, charger_id)
            VALUES ('{}', NULLIF('{}', 'None'), '{}')
        """
        await helperdao.upsert_delete(
            query.format(user_id, charging_schedule_id, charger_id)
        )
    except Exception as e:
        raise MySQLError(str(e))


async def update_new_charging_session(user_id: str, session_id: int, charger_id: str):
    try:
        query = """
            UPDATE home_charging_sessions SET session_id = {} WHERE user_id = '{}'
            and charger_id = '{}' and session_id is NULL ORDER BY
            created_at DESC LIMIT 1
        """
        await helperdao.upsert_delete(query.format(session_id, user_id, charger_id))
    except Exception as e:
        raise MySQLError(str(e))


async def get_specified_connector_status(
    charger_id: str,
    connector_id: str,
    tenant_id: str
):
    try:
        query = f"""
            SELECT status from `tenant{tenant_id}`.`connectors` WHERE
            charger_id = '{charger_id}' and connector_id = '{connector_id}'
        """
        res = await helperdao.fetchone(query)
        if res:
            return res[0]
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_connector_status(charger_id: str):
    try:
        query = f"""
            SELECT status from charger_connector_details WHERE
            charger_id = '{charger_id}'
        """
        res = await helperdao.fetchone(query)
        if res is not None:
            return res[0]
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_charger_details_with_id(location_id: str, day: str, tenant_id: str, charger_id: str):
    try:
        # query = f"""
        #     select l.* , a.*,  lad.*, li.*, c.*, ci.*, cc.* from (
        #     select * from locations where id='{location_id}') as l
        #     left JOIN location_amenities la on l.id=la.location_id
        #     INNER JOIN (select * from active_hours lad where
        #     lad.day='{day}') as lad on l.id=lad.location_id inner join
        #     amenities a on la.amenities_id=a.id left join
        #     location_images li on l.id=li.location_id inner join charger_details c on
        #     c.location_id=l.id inner JOIN charger_connector_details cc on
        #     c.id=cc.charger_id left join charger_images ci on ci.charger_id=c.id;
        # """
        query = f"""
            SELECT
                l.*,
                a.*,
                lad.*,
                c.*,
                cc.*,
                pp.*
            FROM
                (
                SELECT
                    *
                FROM
                    `tenant{tenant_id}`.`locations`
                WHERE
                    id = '{location_id}'
            ) AS l
            LEFT JOIN(
                SELECT
                    *
                FROM
                    `tenant{tenant_id}`.`locations_hours` lad
                WHERE
                    lad.day = '{day}'
            ) AS lad
            ON
                l.id = lad.location_id
            INNER JOIN `tenant{tenant_id}`.`chargers` c ON
                c.location_id = l.id
            INNER JOIN `tenant{tenant_id}`.`charging_plans` pp ON
                c.charging_plan_id = pp.id
            INNER JOIN `tenant{tenant_id}`.`connectors` cc ON
                c.charger_id = cc.charger_id
            LEFT JOIN `tenant{tenant_id}`.`location_amenities` la ON
                l.id = la.location_id
            LEFT JOIN `tenant{tenant_id}`.`amenities` a ON
                la.amenities_id = a.id
            WHERE
                cc.charger_id='{charger_id}';
        """
        res = await helperdao.fetchall_dict(query)
        if res is not None:
            locations = {}
            amenities = {}
            loc_images = {}
            char_images = {}
            charger = {}
            connectors = {}
            for location in res:
                locations.update(
                    {
                        "id": location.get("id"),
                        "name": location.get("label"),
                        "address1": location.get("address_line_1"),
                        "geo_coordinates": location.get("geo_coordinates"),
                        "day": day,
                        "restricted_area": location.get("restricted_area"),
                    }
                )
                if (location.get('is_all_time_available')):
                    location.update({
                        "is_open": True,
                        "from_time": str(time(0, 0, 0)),
                        "to_time": str(time(23, 59, 59)),
                    })
                else:
                    location.update({
                        "is_open": location.get("is_open"),
                        "from_time": str(location.get("start_time")),
                        "to_time": str(location.get("end_time")),
                    })
                amenity_key = location.get("a.id")
                if amenity_key is None or amenity_key in amenities.keys():
                    pass
                else:
                    amenities.update(
                        {
                            amenity_key: {
                                "icon": location.get("icon"),
                                "label": location.get("label"),
                            }
                        }
                    )
                image_key = location.get("li.id")
                if image_key is None or image_key in loc_images.keys():
                    pass
                else:
                    loc_images.update(
                        {image_key: {"image_url": location.get("image_url")}}
                    )
                charger_key = location.get("charger_id")
                organisation_properties = await business_details_and_properties(
                    tenant_id=tenant_id
                )
                price_include_tax = bool(
                    int(organisation_properties.get("price_include_tax", 0))
                )
                if charger_key in charger.keys():
                    pass
                else:
                    bill_by = location.get("billing_type")
                    charger.update(
                        {
                            charger_key: {
                                "id": charger_key,
                                "brand": location.get("brand"),
                                "model": location.get("model"),
                                "type": location.get("type"),
                                "max_output": location.get("max_output"),
                                "bill_by": bill_by,
                                "price": float(location.get("price")),
                                "price_include_tax": price_include_tax,
                            }
                        }
                    )
                charger_image_key = location.get("ci.id", 0)
                if charger_image_key is None or charger_image_key in char_images.keys():
                    pass
                else:
                    char_images.update(
                        {charger_image_key: {
                            "image_url": location.get("ci.image_url")}}
                    )
                connector_key = location.get("connector_id", 0)
                if connector_key in connectors.keys():
                    pass
                else:
                    connectors.update(
                        {
                            connector_key: {
                                "charger_id": location.get("cc.charger_id"),
                                "connector_id": location.get("connector_id"),
                                "max_output": location.get("cc.max_output"),
                                "type": location.get("cc.type"),
                                "status": location.get("status"),
                                "availability": location.get("availability"),
                            }
                        }
                    )
            images = []
            loc_amenities = []
            chargers = []
            for image in loc_images.values():
                images.append(image)
            for image in char_images.values():
                images.append(image)
            for amenity in amenities.values():
                loc_amenities.append(amenity)
            for char in charger.values():
                charger_id = char["id"]
                char["connectors"] = []
                for connector in connectors.values():
                    if connector["charger_id"] == charger_id:
                        char["connectors"].append(connector)
                chargers.append(char)

            locations["chargers"] = chargers
            if len(images):
                locations["images"] = images
            if len(loc_amenities):
                locations["amenities"] = loc_amenities
            return locations
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_session_meter_values(session_id: int, tenant_id: str) -> Any:
    try:
        query = f"""
            SELECT
                s.initial_meter_value,
                smv.energy_import_register,
                smv.energy_import_unit,
                smv.power_import,
                smv.power_import_unit,
                smv.soc,
                s.charger_id
            FROM
                `tenant{tenant_id}`.`sessions` s
            INNER JOIN
                `tenant{tenant_id}`.`sessions_meter_values` smv
            ON
                smv.session_id = s.id
            WHERE
                s.id = {session_id}
            ORDER BY
                smv.created_at
            DESC LIMIT 1
        """
        res = await helperdao.fetchone_dict(query)
        return res
    except Exception as e:
        raise MySQLError(str(e))


# add connector id for charging session as well.


async def get_charging_statistics(
    charger_id: str, to_time: str, from_time: str, span: str
):
    try:
        energy_chart_query_hour = f"""
            select id, hour(start_time), sum(initial_meter_value) as energy_start,
            sum(final_meter_value) as energy_stop from sessions
            where start_time between '{from_time}' and '{to_time}'
            AND charger_id='{charger_id}' group by hour(start_time);
        """

        energy_chart_query_day = f"""
            select id, weekday(start_time), sum(initial_meter_value) as energy_start,
            sum(final_meter_value) as energy_stop from sessions
            where start_time between '{from_time}' and '{to_time}'
            AND charger_id='{charger_id}' group by weekday(start_time);
        """

        energy_chart_query_week = f"""
            select id, week(start_time), sum(initial_meter_value) as energy_start,
            sum(final_meter_value) as energy_stop from sessions
            where start_time between '{from_time}' and '{to_time}'
            AND charger_id='{charger_id}' group by week(start_time);
        """

        energy_user_query = f"""
            select count(t.id), round(ifnull(sum(
            t.final_meter_value - t.initial_meter_value),0),2) as energy_used,
            round(ifnull(sum(timestampdiff(minute,t.start_time,t.stop_time))/60,0),1)
            from sessions t WHERE t.charger_id = '{charger_id}' AND start_time
            between '{from_time}' and '{to_time}'
        """
        data = {}
        res = await helperdao.fetchone(energy_user_query)
        data = {
            "sessions": str(res[0]),
            "energy_used": str(res[1] / 1000) if (res[1] is not None) else str(0),
            "sessions_time": str(res[2]),
        }
        energy_list = []
        chart_query = None
        if span == Span.day:
            chart_query = energy_chart_query_hour
        elif span == Span.week:
            chart_query = energy_chart_query_day
        else:
            chart_query = energy_chart_query_week
        res2 = await helperdao.fetchall(chart_query)
        if res2 is not None:
            for row in res2:
                energy_list.append(
                    {
                        "time": str(row[1]),
                        "energy_start": str(row[2] / 1000)
                        if (row[2] is not None)
                        else str(0),
                        "energy_stop": str(row[3] / 1000)
                        if (row[3] is not None)
                        else str(0),
                    }
                )
            data["energy_list"] = energy_list
            return data
        return None
    except Exception as e:
        raise MySQLError(str(e))


# TODO: not using
async def get_user_password(user_id: uuid, tenant_id: str, business_mobile_app: bool):
    try:
        table = (
            f"`tenant{tenant_id}`.`users`"
            if business_mobile_app
            else "`users`"
        )
        query = f"""
            SELECT password from {table} WHERE id = '{user_id}'
        """
        res = await helperdao.fetchone(query)
        if res is not None:
            return res[0]
        return None
    except Exception as e:
        raise MySQLError(str(e))


# TODO: not using
async def update_user_password(user_id: uuid, new_password: str, tenant_id: str, business_mobile_app: bool):
    try:
        table = (
            f"`tenant{tenant_id}`.`users`"
            if business_mobile_app
            else "`users`"
        )
        query = f"""
            UPDATE {table} SET password='{new_password}' WHERE id = '{user_id}'
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


# async def save_user_token(
#     token: str,
#     user_id: uuid
# ):
#     try:
#         query = f"""
#             UPDATE users set token='{token}' WHERE user_id = '{user_id}'
#         """
#         pool = await MySqlDatabase.get_pool()
#         async with pool.acquire() as conn:
#             async with conn.cursor() as cur:
#                 await cur.execute(query)
#     except Exception as e:
#         raise MySQLError(str(e))


async def update_stop_schedule_id(start_id: str, stop_id: str, charger_id: str):
    try:
        query = f"""
            UPDATE cloudwatch_events SET stop_id='{stop_id}' WHERE
            charger_id='{charger_id}' and start_id='{start_id}'
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def create_new_cloudwatch_event(charger_id: str, start_id: str):
    try:
        query = f"""
            INSERT into cloudwatch_events(charger_id, start_id)
            VALUES('{charger_id}', '{start_id}')
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def get_connector_details(charger_id, connector_id, tenant_id):
    try:
        query = f"""
            SELECT
                pp.price,
                pp.billing_type AS bill_by,
                co.max_output
            FROM
                `tenant{tenant_id}`.`chargers` c
            INNER JOIN `tenant{tenant_id}`.`charging_plans` pp ON
                c.charging_plan_id = pp.id
            INNER JOIN `tenant{tenant_id}`.`connectors` co ON
                co.charger_id = c.charger_id
            WHERE
                c.charger_id = '{charger_id}'
            AND co.connector_id = {connector_id}
        """
        res = await helperdao.fetchone_dict(query)
        if res is not None:
            return res
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_vehicle_details(vehicle_id, tenant_id, business_mobile_app):
    try:
        table = (
            f"`tenant{tenant_id}`.`vehicles`"
            if business_mobile_app
            else "`vehicles`"
        )
        query = f"""
            SELECT * from {table} WHERE id='{vehicle_id}'
        """
        res = await helperdao.fetchone_dict(query)
        return res if res else None
    except Exception as e:
        raise MySQLError(str(e))


async def get_running_session_details(session_ids):
    try:
        query = f"""
            SELECT s.id, cs.end_time, cs.vehicle_id, cs.amount, cs.stop_charging_by,
            l.address_line_1, s.charger_id, s.connector_id, l.label as name from sessions s
            INNER join session_duration cs ON cs.session_id = s.id
            INNER JOIN chargers c on c.charger_id = cs.charger_id
            INNER JOIN locations l on l.id = c.location_id
            WHERE cs.session_id IN ({session_ids}) AND s.is_running=1;
        """
        res = await helperdao.fetchall_dict(query)
        if res is not None:
            session_detail_list = []
            for session in res:
                session_detail_list.append(
                    {
                        "session_id": session["id"],
                        "end_time": str(session["end_time"]),
                        "address1": session["address_line_1"],
                        "charger_id": session["charger_id"],
                        "connector_id": session["connector_id"],
                        "location_name": session["name"],
                        "stop_charging_by": session["stop_charging_by"],
                        "amount": session["amount"],
                        "vehicle_id": session["vehicle_id"],
                    }
                )
            return session_detail_list
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_running_session_details_v2(session_ids, tenant_id, business_mobile_app):
    try:
        table = (
            f"`tenant{tenant_id}`.`vehicles`"
            if business_mobile_app
            else "`vehicles`"
        )
        query = f"""
            SELECT
                s.id,
                s.start_time,
                sp.vehicle_id,
                l.address_line_1,
                s.charger_id,
                s.connector_id,
                co.type as connector_type,
                l.label as name,
                IFNULL(
                    TIMESTAMPDIFF(
                        SECOND,
                        s.start_time,
                        (utc_timestamp)
                    ),
                0) as duration,
                v.image_url,
                v.model,
                v.manufacturer,
                c.charger_name as charger_name
            FROM
                `tenant{tenant_id}`.`sessions` s
            INNER join
                `tenant{tenant_id}`.`session_parameters` sp
            ON
                sp.session_id = s.id
            INNER JOIN
                `tenant{tenant_id}`.`chargers` c
            ON
                c.charger_id = s.charger_id
            INNER JOIN
                `tenant{tenant_id}`.connectors co
            ON
                co.charger_id = s.charger_id
            AND
                co.connector_id=s.connector_id
            INNER JOIN
                `tenant{tenant_id}`.`locations` l
            ON
                l.id = c.location_id
            INNER JOIN
                {table} v
            ON
                v.id = sp.vehicle_id
            WHERE
                s.id IN ({session_ids})
            AND s.is_running=1;
        """
        res = await helperdao.fetchall_dict(query)
        if res is not None:
            session_detail_list = []
            for session in res:
                session_detail_list.append(
                    {
                        "sessionId": session["id"],
                        "locationAddress": session["address_line_1"],
                        "chargerId": session["charger_id"],
                        "chargerName": session["charger_name"],
                        "connectorId": session["connector_id"],
                        "locationName": session["name"],
                        "vehicle": {
                            "model": session["model"],
                            "manufacturer": session["manufacturer"],
                            "image_url": session["image_url"],
                        },
                        "duration": session["duration"],
                        "connectorType": session["connector_type"],
                        "startTime": session["start_time"],
                        "tenantId": tenant_id
                    }
                )
            return session_detail_list
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_current_running_session_id_with_id_tag(id_tag, tenant_id):
    try:
        query = f"""
            SELECT
                id
            FROM
                `tenant{tenant_id}`.`sessions`
            WHERE
                start_id_tag = '{id_tag}'
            AND is_running = 1
            ORDER BY
                created_at
            DESC;
        """
        res = await helperdao.fetchone_dict(query)
        if res:
            return res["id"]
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_current_running_sessions_in_organisations(tenant_id):
    try:
        query = f"""
            SELECT s.id, s.start_id_tag from `tenant{tenant_id}`.`sessions` s
            WHERE s.is_running = 1 ORDER BY s.created_at DESC;
        """
        res = await helperdao.fetchall_dict(query)
        current_sessions_list = []
        if res is not None:
            for r in res:
                current_sessions_list.append(
                    {
                        "id": r["id"],
                        "id_tag": r["start_id_tag"],
                        "tenant_id": tenant_id
                    }
                )
        return current_sessions_list
    except Exception as e:
        raise MySQLError(str(e))


async def add_session_duration(
    id_tag: str,
    charger_id: str,
    connector_id: int,
    end_time: str,
    stop_charging_by: str,
    amount: str,
    session_id: str,
    vehicle_id: str,
    duration_in_minutes: int,
    tenant_id: bool
):
    try:
        query = f"""
            INSERT into `tenant{tenant_id}`.`session_duration`(end_time, id_tag,
            charger_id, connector_id, stop_charging_by, amount,
            session_id, vehicle_id, duration_in_minutes) VALUES ('{end_time}',
            '{id_tag}', '{charger_id}', {connector_id}, '{stop_charging_by}',
            '{amount}','{session_id}','{vehicle_id}', '{duration_in_minutes}');
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def add_session_paramters(
    id_tag: str,
    charger_id: str,
    connector_id: int,
    stop_charging_by: str,
    session_id: str,
    vehicle_id: str,
    duration_in_minutes: int,
    price: float,
    plan_type: str,
    total_energy: float,
    price_id: str,
    billing_by: str,
    tenant_id: str,
    user_id: str,
    apply_after: str,
    idle_charging_fee: str,
    fixed_starting_fee: str,
):
    try:
        query = f"""
            INSERT INTO `tenant{tenant_id}`.`session_parameters`(
                `id_tag`,
                `charger_id`,
                `connector_id`,
                `vehicle_id`,
                `user_id`,
                `session_id`,
                `price`,
                `charging_plan_id`,
                `billing_type`,
                `plan_type`,
                `max_energy_consumption`,
                `duration_in_minutes`,
                `stop_charging_by`,
                `fixed_starting_fee`,
                `apply_after`,
                `idle_charging_fee`,
                `created_at`,
                `updated_at`
            )
            VALUES(
                '{id_tag}',
                '{charger_id}',
                '{connector_id}',
                '{vehicle_id}',
                '{user_id}',
                '{session_id}',
                '{price}',
                '{price_id}',
                '{billing_by}',
                '{plan_type}',
                '{total_energy}',
                '{duration_in_minutes}',
                '{stop_charging_by}',
                '{fixed_starting_fee}',
                '{apply_after}',
                '{idle_charging_fee}',
                '{datetime.utcnow()}',
                '{datetime.utcnow()}'
            )
        """
        LOGGER.info(query)
        await helperdao.upsert_delete(query)
        return
    except Exception as e:
        raise MySQLError(str(e))


async def update_user(user_id: str, name: str, email: str, gender: str, dob: str):
    try:
        query = f"""
            UPDATE `users` SET `email`='{email}' WHERE `user_id`='{user_id}';
            UPDATE `user_details` SET `name`='{name}' WHERE `user_id`='{user_id}';
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def update_userv2(
    user_id: str,
    name: str,
    email: str,
    address: str,
    token: str,
    os: str,
    tenant_id: str,
    business_mobile_app: str
):
    try:
        existing_user_detail = await get_user_details_with_user_id(
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app
        )

        table = (
            f"`tenant{tenant_id}`.`customer_invites`"
            if business_mobile_app
            else "`customer_invites`"
        )
        user_table = (
            f"`tenant{tenant_id}`.`users`"
            if business_mobile_app
            else "`users`"
        )
        query = ""
        query1 = f"""
            UPDATE {table} SET `name`='{name}'
            WHERE `user_id`='{user_id}';
            UPDATE {user_table} SET `name`='{name}'
            WHERE `id`='{user_id}';
        """

        query2 = f"""
            UPDATE {table} SET `email`='{email}' WHERE `user_id`='{user_id}';
            UPDATE {user_table} SET `email`='{email}', `email_verified_at`=null
            WHERE `id`='{user_id}';
        """

        query3 = f"""
            UPDATE {table} SET `token`='{token}', `os` = '{os}'
            WHERE `user_id`='{user_id}';
        """

        query4 = f"""
            UPDATE {table} SET `address`='{address}' WHERE `user_id`='{user_id}';
        """

        if name is not None and name != "" and name != existing_user_detail["name"]:
            query += query1
        if email is not None and email != "" and email != existing_user_detail["email"]:
            query += query2
        if token is not None and token != "" and token != existing_user_detail["token"]:
            query += query3
        if (
            address is not None
            and address != ""
            and address != existing_user_detail["address"]
        ):
            query += query4
        if query:
            await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def get_charging_history(user_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`vehicles`"
        if business_mobile_app
        else "`vehicles`"
    )
    query = f"""
        select pb.*, v.* from `tenant{tenant_id}`.`business_transactions` pb
        INNER JOIN {table} v on pb.vehicle_id=v.id WHERE pb.user_id='{user_id}'
        ORDER BY pb.created_at DESC;
    """
    res = await helperdao.fetchall_dict(query)
    rows = []
    if res is not None:
        for i in res:
            rows.append(
                {
                    "vehicle_id": i.get("vehicle_id"),
                    "vehicle_brand": i.get("manufacturer"),
                    "vehicle_model": i.get("model"),
                    "vehicle_image": i.get("image_url"),
                    "amount": i.get("charging_cost_with_tax"),
                    "time": str(i.get("created_at")),
                }
            )
        return rows
    return None


async def get_user_verification_details(user_id: str) -> Any:
    try:
        query = f"""
            SELECT u.user_id, ud.name, u.email, ud.is_email_verified
            FROM users u INNER JOIN user_details ud ON
            u.user_id=ud.user_id WHERE u.user_id = '{user_id}'
        """
        res = await helperdao.fetchone(query)
        if res is not None:
            return (res[0], res[1], res[2], bool(res[3]))
        return (None, None, None, None)
    except Exception as e:
        raise MySQLError(str(e))


async def charger_location_id(charger_id: str, tenant_id: str):
    try:
        query = f"""
            SELECT
                location_id
            FROM
                `tenant{tenant_id}`.`chargers`
            WHERE charger_id = '{charger_id}'
        """
        res = await helperdao.fetchone(query)
        if res is not None:
            return int(res[0])
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_token_details(user_id):
    try:
        query = f"""
            SELECT `verification_token`, `token_expire` FROM `email_verification`
            WHERE `user_id`='{user_id}' ORDER BY `id` DESC
        """
        res = await helperdao.fetchone(query)
        if res is not None:
            return res[0], res[1]
        return None, None
    except Exception as e:
        raise MySQLError(str(e))


async def verify_user(user_id):
    try:
        query = f"""
            UPDATE `user_details` SET `is_email_verified`='{1}'
            WHERE `user_id`='{user_id}';
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def insert_verification_token(user_id, verification_token, token_expire):
    try:
        query = f"""
            INSERT INTO `email_verification`(`user_id`, `verification_token`,
            `token_expire`) VALUES ('{user_id}','{verification_token}',
            '{token_expire}');
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def get_session_duration_details(session_id):
    try:
        query = f"""
            SELECT
                s.id,
                cs.end_time,
                cs.amount,
                cs.vehicle_id,
                cs.stop_charging_by,
                pp.billing_type,
                pp.price,
                s.charger_id,
                s.connector_id,
                s.start_id_tag,
                s.initial_meter_value
            FROM
                sessions s
            INNER JOIN session_duration cs ON
                cs.session_id = s.id
            INNER JOIN chargers c ON
                c.charger_id = cs.charger_id
            INNER JOIN price_plans pp ON
                c.price_id=pp.price_id
            WHERE
                cs.session_id = '{session_id}';
        """
        res = await helperdao.fetchone_dict(query)
        if res is not None:
            return {
                "session_id": res["id"],
                "end_time": str(res["end_time"]),
                "amount": str(res["amount"]),
                "stop_charging_by": res["stop_charging_by"],
                "bill_by": res["billing_type"],
                "price": res["price"],
                "charger_id": res["charger_id"],
                "connector_id": res["connector_id"],
                "start_id_tag": res["start_id_tag"],
                "vehicle_id": res["vehicle_id"],
                "initial_meter_value": res["initial_meter_value"],
            }
        return None
    except Exception as e:
        raise MySQLError(str(e))


async def get_device_token(user_id: str, tenant_id: str):
    try:
        business_mobile_app = await does_business_have_mobile_app(tenant_id)
        table = (
            f"`tenant{tenant_id}`.`customer_invites`"
            if business_mobile_app
            else "`customer_invites`"
        )
        query = f"""
            SELECT
                `token`, `os`
            FROM
                {table}
            WHERE `user_id` = '{user_id}'
        """
        res = await helperdao.fetchone_dict(query)
        return res if res else {}
    except Exception as e:
        raise MySQLError(str(e))


async def save_user_token(
    token: str,
    os: str,
    user_id: uuid,
    tenant_id: str,
    business_mobile_app: bool
):
    try:
        table = (
            f"`tenant{tenant_id}`.`customer_invites`"
            if business_mobile_app
            else "`customer_invites`"
        )
        query = f"""
            UPDATE {table} set token='{token}', os='{os}'
            WHERE user_id = '{user_id}'
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def get_user_default_vehicle(
    user_id: str, tenant_id: str, business_mobile_app: bool
):
    try:
        user_table = (
            f"`tenant{tenant_id}`.`user_vehicles`"
            if business_mobile_app
            else "`user_vehicles`"
        )
        query = f"""
            SELECT
                `vehicle_id`
            FROM
                {user_table}
            WHERE
                `is_default` = 1
            AND `user_id` = '{user_id}'
        """
        LOGGER.info(query)
        res = await helperdao.fetchone_dict(query)
        LOGGER.info(res)
        return res.get("vehicle_id") if res is not None else res
    except Exception as e:
        raise MySQLError(str(e))


async def check_user_have_private_plans(
    user_id: str, charger_id: str, connector_id: str, tenant_id: str
):
    try:
        query = f"""
            SELECT
                cc.`charging_plan_id`
            FROM
                `tenant{tenant_id}`.`customer_invites` ci
            INNER JOIN
                `tenant{tenant_id}`.`customer_connectors` cc
            ON
                ci.id=cc.customer_invite_id
            INNER JOIN `tenant{tenant_id}`.`connectors` c
                ON cc.connector_row_id=c.id
            WHERE
                ci.user_id = '{user_id}'
            AND
                c.charger_id = '{charger_id}'
            AND
                c.connector_id = '{connector_id}'
            AND cc.deleted_at is null
        """
        res = await helperdao.fetchone_dict(query)
        return res.get("charging_plan_id") if res else 0
    except Exception as e:
        raise MySQLError(str(e))


async def get_pricing_plan(price_id: str, tenant_id: str):
    try:
        query = f"""
            SELECT
                *
            FROM
                `tenant{tenant_id}`.`charging_plans`
            WHERE
                `id`={price_id}
        """
        LOGGER.info(query)
        res = await helperdao.fetchone_dict(query)
        return res if res else {}
    except Exception as e:
        raise MySQLError(str(e))


async def get_charging_plan_of_location(charger_id: str, tenant_id: str):
    try:
        query = f"""
            SELECT
                l.`charging_plan_id`
            FROM
                `tenant{tenant_id}`.`chargers` c
            INNER JOIN
                `tenant{tenant_id}`.`locations` l
            ON
                c.location_id=l.id
            WHERE
                `charger_id` = '{charger_id}';
        """
        LOGGER.info(query)
        res = await helperdao.fetchone_dict(query=query)
        return res.get("charging_plan_id") if res else 0
    except Exception as e:
        raise MySQLError(str(e))


async def get_charging_plan_of_connector(
    tenant_id: str, charger_id: str, connector_id: str
):
    try:
        query = f"""
            SELECT
                `charging_plan_id`
            FROM
                `tenant{tenant_id}`.`connectors`
            WHERE
                `charger_id` = '{charger_id}'
            AND `connector_id` = '{connector_id}';
        """
        res = await helperdao.fetchone_dict(query=query)
        return res.get("charging_plan_id") if res else 0
    except Exception as e:
        raise MySQLError(str(e))


async def get_recent_charging_stations(user_id: str, day: str, tenant_id: str):
    try:
        location_ids = []
        query = f"""
            SELECT DISTINCT
                c.location_id
            FROM
                `tenant{tenant_id}`.`business_transactions` psd
            INNER JOIN `tenant{tenant_id}`.`chargers` c ON
                psd.charger_id = c.charger_id
            WHERE
                psd.user_id='{user_id}'
            ORDER BY
                psd.id DESC
            LIMIT 3;
        """
        res = await helperdao.fetchall_dict(query)
        if res is not None:
            for location in res:
                location_ids.append(location["location_id"])
        return location_ids
    except Exception as e:
        LOGGER.error(e)
        raise MySQLError(str(e))


async def get_additional_details_from_session_parameters(session_id, tenant_id):
    try:
        query = f"""
        SELECT
            `charger_id`,
            `connector_id`,
            `vehicle_id`,
            `session_id`,
            `price`,
            `charging_plan_id` as price_id,
            `plan_type`,
            `max_energy_consumption`,
            `duration_in_minutes`,
            `stop_charging_by`,
            `user_id`
        FROM
            `tenant{tenant_id}`.`session_parameters`
        WHERE
            `session_id`='{session_id}';
        """
        res = await helperdao.fetchone_dict(query)
        return res
    except Exception as e:
        LOGGER.error(e)
        raise e


async def get_additional_details_from_session_duration(session_id):
    try:
        query = f"""
            SELECT
                `sd`.`end_time`,
                `sd`.`duration_in_minutes`,
                `sd`.`amount`,
                `sd`.`stop_charging_by`,
                `sd`.`id_tag`,
                `sd`.`charger_id`,
                `sd`.`connector_id`,
                `sd`.`vehicle_id`,
                `sd`.`session_id`,
                `pp`.`price`,
                `pp`.`price_id`,
                `pp`.`billing_type`,
                `rc`.`user_id`
            FROM
                `session_duration` sd
            INNER JOIN `rfid_cards` rc ON
                sd.id_tag = rc.id_tag
            INNER JOIN `chargers` c ON
                c.charger_id = sd.charger_id
            INNER JOIN `price_plans` pp ON
                pp.price_id = c.price_id
            WHERE
                `sd`.`session_id` = '{session_id}';
        """
        res = await helperdao.fetchone_dict(query)
        return res
    except Exception as e:
        LOGGER.error(e)
        raise e


async def get_price_details_by_price_id(price_id, tenant_id):
    try:
        price_plan_query = f"""
            SELECT * FROM `tenant{tenant_id}`.`charging_plans` WHERE `id`='{price_id}'
            """
        res = await helperdao.fetchone_dict(price_plan_query)
        return res if res else {}
    except Exception as e:
        LOGGER.error(e)
        raise e


async def get_session_related_parameters(session_id, tenant_id) -> Any:
    try:
        query = f"""
            SELECT
                l.id as location_id,
                l.label as location_name,
                c.charger_id as charger_id,
                cc.max_output,
                cc.type AS connector_type,
                cc.connector_id as connector_id,
                s.final_meter_value,
                s.initial_meter_value,
                s.start_time as session_start_time,
                IFNULL(
                    TIMESTAMPDIFF(
                        SECOND,
                        s.start_time,
                        s.stop_time
                    ),
                    0
                ) AS elapsed_time
            FROM
                `tenant{tenant_id}`.`sessions` s
            INNER JOIN `tenant{tenant_id}`.`chargers` c ON
                c.charger_id = s.charger_id
            INNER JOIN `tenant{tenant_id}`.`connectors` cc ON
                cc.charger_id = c.charger_id
            INNER JOIN `tenant{tenant_id}`.`locations` l ON
                l.id = c.location_id
            WHERE
                s.id = {session_id};
        """
        res = await helperdao.fetchone_dict(query=query)
        return res
    except Exception as e:
        LOGGER.error(e)


async def get_charger_pricing_plan(charger_id, tenant_id, connector_id):
    query = f"""
        SELECT
            `label`,
            pp.`type`,
            `billing_type`,
            `price`
        FROM
            `tenant{tenant_id}`.`charging_plans` pp
        INNER JOIN `tenant{tenant_id}`.`connectors` c ON
            pp.id=c.charging_plan_id
        WHERE
            c.charger_id='{charger_id}'
        AND c.connector_id='{connector_id}';
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def get_session_detail(session_id, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`sessions`
        WHERE
            `id`={session_id};
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def get_organisation_properties(tenant_id):
    query = f"""
        SELECT
            bs.*
        FROM
            `businesses` b
        INNER JOIN
            `business_settings` bs
        ON b.id=bs.business_id
        WHERE
            `b`.`tenant_id` = '{tenant_id}';
    """
    res = await helperdao.fetchone_dict(query=query)
    return res if res else {}


async def get_organisations_property(org_ids, parameter_key):
    query = f"""
        SELECT
            `org_id`,
            `parameter_value`
        FROM
            `organisation_properties`
        WHERE
            `parameter_key`= '{parameter_key}'
            AND `org_id` IN ('{org_ids}');
    """
    res = await helperdao.fetchall_dict(query=query)
    if res:
        res = {item["org_id"]: item["parameter_value"] for item in res}
    return res if res else {}


async def get_id_tag_detail(id_tag):
    query = f"""
        SELECT
            `user_id`,
            `is_blocked`,
            `expiry_date`,
            `org_id`,
            `is_parent`,
            `parent_id_tag`
        FROM
            `rfid_cards`
        WHERE
            `id_tag` = '{id_tag}'
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def get_session_invoice(session_id, tenant_id):
    query = f"""
        SELECT
            `inv`.`id` AS invoice_id,
            `inv`.`created_at` AS invoice_date,
            `inv`.`session_id`,
            `inv`.`charger_id`,
            `inv`.`connector_id`,
            `inv`.`charging_cost`,
            `inv`.`tax_percentage`,
            `inv`.`charging_cost_with_tax`,
            `inv`.`gateway_fee`,
            `inv`.`bill_by`,
            `inv`.`price`,
            `u`.`name`,
            `u`.`phone`,
            `inv`.`location_name`,
            `inv`.`session_energy_used`,
            `inv`.`idle_charging_cost` AS idle_charging_cost,
            `s`.`start_time`,
            `s`.`stop_time`,
            `inv`.`session_runtime` AS duration,
            `cc`.`max_output`
        FROM
            `tenant{tenant_id}`.`business_transactions` inv
        INNER JOIN `tenant{tenant_id}`.`customer_invites` u ON
            inv.user_id = u.user_id
        INNER JOIN `tenant{tenant_id}`.`sessions` s ON
            inv.session_id = s.id
        INNER JOIN `tenant{tenant_id}`.`connectors` cc ON
            inv.charger_id=cc.charger_id
        AND inv.connector_id=cc.connector_id
        WHERE
            inv.`session_id` = '{session_id}'
    """
    # query = f"""
    #     SELECT
    #         psd.id AS invoice_id,
    #         psd.created_at AS invoice_date,
    #         psd.session_id,
    #         psd.charger_id,
    #         psd.connector_id,
    #         psd.charging_cost,
    #         psd.tax_percent,
    #         psd.charging_cost_with_tax,
    #         u.name,
    #         u.phone,
    #         l.label as name,
    #         ROUND(
    #             (
    #                 final_meter_value - initial_meter_value
    #             ) / 1000,
    #             2
    #         ) AS energy_used,
    #         s.start_time,
    #         s.stop_time,
    #         ROUND(
    #             TIMESTAMPDIFF(
    #                 MINUTE,
    #                 s.start_time,
    #                 s.stop_time
    #             ) / 60,
    #             1
    #         ) AS session_time,
    #         sp.duration_in_minutes
    #     FROM
    #         sessions s
    #     INNER JOIN public_session_details psd ON
    #         psd.session_id = s.id
    #     INNER JOIN users u ON
    #         psd.user_id = u.user_id
    #     INNER JOIN charger_details c ON
    #         psd.charger_id = c.id
    #     INNER JOIN locations l ON
    #         c.location_id = l.id
    #     INNER JOIN session_parameters sp ON
    #         sp.session_id = s.id
    #     WHERE
    #         s.id = '{session_id}';
    # """
    res = await helperdao.fetchone_dict(query)
    return res


async def get_organisation_detail(org_id):
    query = f"""
        SELECT
            *
        FROM
            `organisations` o
        WHERE
            o.org_id = '{org_id}';
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def insert_invoice(
    charger_id,
    charger_type,
    connector_id,
    connector_type,
    connector_maxoutput,
    location_id,
    location_name,
    session_id,
    session_start_time,
    session_runtime,
    session_energy_used,
    bill_by,
    price,
    currency,
    charging_cost,
    tax_percentage,
    charging_cost_with_tax,
    user_id,
    vehicle_id,
    gateway_fee,
    tenant_id,
    charging_plan_id,
    payment_gateway="wallet",
    payment_mode="wallet",
):
    query = f"""
        INSERT INTO `tenant{tenant_id}`.`business_transactions`(
            `charger_id`,
            `charger_type`,
            `connector_id`,
            `connector_type`,
            `connector_maxoutput`,
            `location_id`,
            `location_name`,
            `session_id`,
            `session_start_time`,
            `session_runtime`,
            `session_energy_used`,
            `bill_by`,
            `price_group_name`,
            `payment_gateway`,
            `payment_mode`,
            `price`,
            `currency`,
            `charging_cost`,
            `tax_percentage`,
            `charging_cost_with_tax`,
            `user_id`,
            `vehicle_id`,
            `idle_minutes`,
            `idle_price`,
            `idle_charging_cost`
        ) VALUES (
            '{charger_id}',
            '{charger_type}',
            '{connector_id}',
            '{connector_type}',
            '{connector_maxoutput}',
            '{location_id}',
            '{location_name}',
            '{session_id}',
            '{session_start_time}',
            '{session_runtime}',
            '{session_energy_used}',
            '{bill_by}',
            '{charging_plan_id}',
            '{payment_gateway}',
            '{payment_mode}',
            '{price}',
            '{currency}',
            '{charging_cost}',
            '{tax_percentage}',
            '{charging_cost_with_tax}',
            '{user_id}',
            '{vehicle_id}',
            '{0}',
            '{0}',
            '{0}'
        )
    """
    res = await helperdao.upsert_delete(query)
    return res


async def get_invoice_by_id(invoice_id):
    query = f"""
        SELECT
            *
        FROM
            `invoice`
        WHERE
            `id`='{invoice_id}'
    """
    res = await helperdao.fetchone_dict(query=query)
    if res:
        charging_cost_with_tax = round(res.get("charging_cost_with_tax"), 2)
        idle_charging_cost = round(res.get("idle_charging_cost", 0), 2)
        invoice = {
            "invoice": {
                "invoice_id": invoice_id,
                "charger_id": res.get("charger_id"),
                "charger_type": res.get("charger_type"),
                "connector": {
                    "id": res.get("connector_id"),
                    "type": res.get("connector_type"),
                    "max_output": f"{res.get('connector_maxoutput')}KW",
                },
                "location": res.get("location_name"),
                "session": {
                    "session_id": res.get("session_id"),
                    "elapsed_time": str(res.get("session_runtime")),
                    "total_energy_used": f"{res.get('session_energy_used'):.2f}",
                },
                "bill_by": res.get("bill_by"),
                "price": res.get("price"),
                "currency": res.get("currency"),
                "charging_cost": round(res.get("charging_cost"), 2),
                "tax_percent": res.get("tax_percentage"),
                "charging_cost_with_tax": charging_cost_with_tax,
                "idle_charging_cost": idle_charging_cost,
                "final_cost": charging_cost_with_tax + idle_charging_cost,
                "user_id": res.get("user_id"),
                "vehicle_id": res.get("vehicle_id"),
            },
        }
        return invoice
    return None


async def get_invoice_by_session_id(session_id, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`business_transactions`
        WHERE
            `session_id`='{session_id}'
    """
    res = await helperdao.fetchone_dict(query=query)
    if res:
        charging_cost_with_tax = round(res.get("charging_cost_with_tax"), 2)
        idle_charging_cost = (
            res.get("idle_charging_cost") if res.get(
                "idle_charging_cost") else 0
        )
        idle_charging_cost = round(idle_charging_cost, 2)
        return {
            "invoice": {
                "invoice_id": res.get("id"),
                "charger_id": res.get("charger_id"),
                "charger_type": res.get("charger_type"),
                "connector": {
                    "id": res.get("connector_id"),
                    "type": res.get("connector_type"),
                    "max_output": res.get("connector_maxoutput"),
                },
                "location": res.get("location_name"),
                "session": {
                    "session_id": res.get("session_id"),
                    "session_start_time": str(res.get("session_start_time")),
                    "elapsed_time": str(res.get("session_runtime")),
                    "total_energy_used": f"{res.get('session_energy_used'):.2f}",
                },
                "bill_by": res.get("bill_by"),
                "tax_percent": res.get("tax_percentage"),
                "price": res.get("price"),
                "currency": res.get("currency"),
                "charging_cost": round(res.get("charging_cost"), 2),
                "service_fee": round(
                    res.get("gateway_fee", 0)
                    + res.get("fixed_starting_fee"), 2
                ),
                "idle_charging_cost": res.get("idle_charging_cost", 0),
                "total_tax": res.get("total_tax"),
                "final_cost": res.get("final_amount"),
                "charging_cost_with_tax": charging_cost_with_tax,
                "idle_price": res.get("idle_price"),
                "idle_minutes": res.get("idle_minutes"),
                "user_id": res.get("user_id"),
                "vehicle_id": res.get("vehicle_id"),
            },
        }

    return None


async def get_users_sessions(user_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`vehicles`"
        if business_mobile_app
        else "`vehicles`"
    )
    query = f"""
        SELECT
            `inv`.`id` AS invoice_id,
            `inv`.`charger_id`,
            `inv`.`charger_type`,
            `inv`.`connector_id`,
            `inv`.`connector_type`,
            `inv`.`connector_maxoutput`,
            `inv`.`location_id`,
            `inv`.`location_name`,
            `inv`.`session_id`,
            `inv`.`session_runtime`,
            `inv`.`session_energy_used`,
            `inv`.`bill_by`,
            `inv`.`tax_percentage`,
            `inv`.`price`,
            `inv`.`currency`,
            `inv`.`charging_cost`,
            `inv`.`gateway_fee`,
            `inv`.`fixed_starting_fee`,
            `inv`.`idle_charging_cost`,
            `inv`.`total_tax`,
            `inv`.`final_amount`,
            `inv`.`charging_cost_with_tax`,
            `inv`.`user_id`,
            `inv`.`vehicle_id`,
            `inv`.`idle_minutes`,
            `inv`.`idle_price`,
            `s`.`start_time`,
            `v`.`model`,
            `v`.`manufacturer`,
            `v`.`image_url`
        FROM
            `tenant{tenant_id}`.`business_transactions` inv
        INNER JOIN `tenant{tenant_id}`.`sessions` s ON
            inv.session_id = s.id
        INNER JOIN {table} v ON
            v.id = inv.vehicle_id
        WHERE
            inv.user_id = '{user_id}'
        ORDER BY
            s.start_time
        DESC
            ;
    """
    res = await helperdao.fetchall_dict(query)
    sessions = {}
    sessionsList = []

    if res:
        for session in res:
            start_time: datetime = session.get("start_time")
            key = start_time.date()
            session["start_date"] = str(key)
            session["service_fee"] = round(
                session.get("gateway_fee", 0)
                + session.get("fixed_starting_fee", 0), 2
            )
            session["final_cost"] = session.get("final_amount", 0)
            session["tenant_id"] = tenant_id

            if key in sessions.keys():
                sessions[key].append(session)
            else:
                sessions[key] = [session]

        for session in sessions:
            sessionsList.append(sessions[session])

    return sessionsList


async def insert_stripe_payment_info(payment_id, user_id, amount, tenant_id):
    query = f"""
        INSERT INTO `tenant{tenant_id}`.`stripe_payments`(
            `payment_id`,
            `amount_added`,
            `user_id`
        )
        VALUES(
            '{payment_id}',
            '{amount}',
            '{user_id}'
        )
    """
    res = await helperdao.upsert_delete(query)
    return res


async def get_wallet_history(user_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`vehicles`"
        if business_mobile_app
        else "`vehicles`"
    )

    query = f"""
        SELECT
            `inv`.`id` AS invoice_id,
            `inv`.`charger_id`,
            `inv`.`charger_type`,
            `inv`.`connector_id`,
            `inv`.`connector_type`,
            `inv`.`connector_maxoutput`,
            `inv`.`location_id`,
            `inv`.`location_name`,
            `inv`.`session_id`,
            `inv`.`session_runtime`,
            `inv`.`session_energy_used`,
            `inv`.`bill_by`,
            `inv`.`price`,
            `inv`.`currency`,
            `inv`.`charging_cost`,
            `inv`.`tax_percentage`,
            `inv`.`charging_cost_with_tax`,
            `inv`.`user_id`,
            `inv`.`vehicle_id`,
            `inv`.`idle_minutes`,
            `inv`.`idle_price`,
            `inv`.`fixed_starting_fee`,
            `inv`.`idle_charging_cost`,
            `inv`.`gateway_fee`,
            `inv`.`total_cost_without_tax`,
            `inv`.`total_tax`,
            `inv`.`final_amount` as final_cost,
            `s`.`start_time`,
            `v`.`model`,
            `v`.`manufacturer`,
            `v`.`image_url`
        FROM
            `tenant{tenant_id}`.`business_transactions` inv
        INNER JOIN `tenant{tenant_id}`.`sessions` s ON
            inv.session_id = s.id
        INNER JOIN {table} v ON
            v.id = inv.vehicle_id
        WHERE
            inv.user_id = '{user_id}'
        GROUP BY inv.session_id
        ORDER BY
            s.start_time
        DESC
            ;
    """
    sessions_result = await helperdao.fetchall_dict(query)
    table_history = (
        f"`tenant{tenant_id}`.`payment_transactions`"
        if business_mobile_app
        else "`payment_transactions`"
    )

    query = f"""
    SELECT
        `merchantPaymentId`,
        `amount`,
        `user_id`,
        `created_at`,
        `status`
    FROM
        {table_history}
    WHERE
        `user_id`='{user_id}'
    ORDER BY
        created_at
    DESC
    """
    stripe_info_result = await helperdao.fetchall_dict(query)

    combined_result = []

    if stripe_info_result and sessions_result:
        combined_result = stripe_info_result + sessions_result
    elif stripe_info_result:
        combined_result = stripe_info_result
    elif sessions_result:
        combined_result = sessions_result
    return combined_result


async def sort_history_and_arrange_by_date(combined_result, arrange_by_date=True):
    def get_datetime(item):
        if "created_at" in item:
            return item["created_at"]
        elif "start_time" in item:
            return item["start_time"]
        else:
            return None

    def get_date(item):
        if "created_at" in item:
            return item["created_at"].date()
        elif "start_time" in item:
            return item["start_time"].date()
        else:
            return None
    sorted_result = sorted(
        combined_result, key=lambda x: get_datetime(x), reverse=True)

    if not arrange_by_date:
        return sorted_result

    history = {}
    historyList = []

    for item in sorted_result:
        date = get_date(item)
        if date not in history:
            history[date] = []
        history[date].append(item)
        if "created_at" in item:
            item["created_at"] = str(item["created_at"])
        if "start_time" in item:
            item["start_time"] = str(item["start_time"])
    for i in history:
        historyList.append(history[i])
    return historyList


async def get_phonepe_wallet_history(user_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`vehicles`"
        if business_mobile_app
        else "`vehicles`"
    )
    query = f"""
        SELECT
            `inv`.`id` AS invoice_id,
            `inv`.`charger_id`,
            `inv`.`charger_type`,
            `inv`.`connector_id`,
            `inv`.`connector_type`,
            `inv`.`connector_maxoutput`,
            `inv`.`location_id`,
            `inv`.`location_name`,
            `inv`.`session_id`,
            `inv`.`session_runtime`,
            `inv`.`session_energy_used`,
            `inv`.`bill_by`,
            `inv`.`price`,
            `inv`.`currency`,
            `inv`.`charging_cost`,
            `inv`.`tax_percentage`,
            `inv`.`charging_cost_with_tax`,
            `inv`.`user_id`,
            `inv`.`vehicle_id`,
            `v`.`manufacturer`,
            `v`.`model`,
            `v`.`image_url`,
            `s`.`start_time`
        FROM
            `tenant{tenant_id}`.`business_transactions` inv
        INNER JOIN `tenant{tenant_id}`.`sessions` s ON
            inv.session_id = s.id
        INNER JOIN {table} v ON
            v.id = inv.vehicle_id
        WHERE
            inv.user_id = '{user_id}'
        GROUP BY inv.session_id
        ORDER BY
            s.start_time
        DESC
            ;
    """
    sessions_result = await helperdao.fetchall_dict(query)
    query = f"""
    SELECT
        IFNULL(phonepeTransactionId, 'NA') as phonepeTransactionId,
        `amount`,
        `userId`,
        `state`,
        `created_at`
    FROM
        `tenant{tenant_id}`.`phonepe_transactions`
    WHERE
        `userId`='{user_id}' AND `amount` != 'NULL'
    ORDER BY
        created_at
    DESC
    """
    stripe_info_result = await helperdao.fetchall_dict(query)

    combined_result = []

    if stripe_info_result and sessions_result:
        combined_result = stripe_info_result + sessions_result
    elif stripe_info_result:
        combined_result = stripe_info_result
    elif sessions_result:
        combined_result = sessions_result

    return combined_result


async def get_maib_wallet_history(user_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`vehicles`"
        if business_mobile_app
        else "`vehicles`"
    )
    query = f"""
        SELECT
            `inv`.`id` AS invoice_id,
            `inv`.`charger_id`,
            `inv`.`charger_type`,
            `inv`.`connector_id`,
            `inv`.`connector_type`,
            `inv`.`connector_maxoutput`,
            `inv`.`location_id`,
            `inv`.`location_name`,
            `inv`.`session_id`,
            `inv`.`session_runtime`,
            `inv`.`session_energy_used`,
            `inv`.`bill_by`,
            `inv`.`price`,
            `inv`.`currency`,
            `inv`.`charging_cost`,
            `inv`.`tax_percentage`,
            `inv`.`charging_cost_with_tax`,
            `inv`.`user_id`,
            `inv`.`vehicle_id`,
            `v`.`manufacturer`,
            `v`.`model`,
            `v`.`image_url`,
            `s`.`start_time`
        FROM
            `tenant{tenant_id}`.`business_transactions` inv
        INNER JOIN `tenant{tenant_id}`.`sessions` s ON
            inv.session_id = s.id
        INNER JOIN {table} v ON
            v.id = inv.vehicle_id
        WHERE
            inv.user_id = '{user_id}'
        GROUP BY inv.session_id
        ORDER BY
            s.start_time
        DESC
            ;
    """
    sessions_result = await helperdao.fetchall_dict(query)
    query = f"""
    SELECT
        IFNULL(transaction_id, 'NA') as maibTransactionId,
        amount,
        user_id,
        result,
        created_at
    FROM `tenant{tenant_id}`.`maib_transactions`
    WHERE user_id='{user_id}' AND amount!= 'NULL'
    ORDER BY
        created_at
    DESC;
    """
    stripe_info_result = await helperdao.fetchall_dict(query)

    combined_result = []

    if stripe_info_result and sessions_result:
        combined_result = stripe_info_result + sessions_result
    elif stripe_info_result:
        combined_result = stripe_info_result
    elif sessions_result:
        combined_result = sessions_result

    return combined_result


async def get_user_details(user_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`customer_invites`"
        if business_mobile_app
        else "`customer_invites`"
    )
    query = f"""
        SELECT
            *
        FROM
            {table}
        WHERE
            user_id='{user_id}';
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def get_charger_detail(charger_id, connector_id, tenant_id):
    try:
        query = f"""
            SELECT
                c.charger_id,
                c.model,
                pp.price,
                pp.billing_type,
                pp.fixed_starting_fee,
                pp.idle_charging_fee,
                pp.apply_after,
                co.charger_id,
                co.connector_id,
                co.max_output,
                co.type,
                co.status,
                co.availability,
                c.location_id
            FROM
                `tenant{tenant_id}`.`chargers` c
            INNER JOIN `tenant{tenant_id}`.`connectors` co ON
                co.charger_id = c.charger_id
            INNER JOIN `tenant{tenant_id}`.`charging_plans` pp ON
                c.charging_plan_id = pp.id
            INNER JOIN `tenant{tenant_id}`.`locations` l ON
                c.location_id = l.id
            WHERE c.charger_id='{charger_id}'
            AND co.connector_id='{connector_id}';
        """
        chargers_dict = await helperdao.fetchone_dict(query)
        chargers_dict["charger_id"] = chargers_dict.pop("charger_id")
        chargers_dict["connector"] = {
            "connector_id": chargers_dict.pop("connector_id"),
            "type": chargers_dict.pop("type"),
            "connector_status": chargers_dict.pop("status"),
            "max_output": chargers_dict.pop("max_output"),
            "bill_by": chargers_dict.pop("billing_type"),
            "price": float(chargers_dict.pop("price")),
            "apply_after": chargers_dict.pop("apply_after"),
            "fixed_starting_fee": float(chargers_dict.pop("fixed_starting_fee")),
            "idle_charging_fee": float(chargers_dict.pop("idle_charging_fee"))
        }
        return chargers_dict
    except Exception as e:
        raise MySQLError(str(e))


async def get_charger_location(locations_id: list, day: str, tenant_id: str):
    try:
        location_query = f"""
            SELECT * FROM `tenant{tenant_id}`.`locations` l
            WHERE l.id='{locations_id}'
        """
        day_query = f"""
            SELECT
                `day`,
                `start_time` as from_time,
                `end_time` as to_time,
                `is_active` as is_open
            FROM
                `locations_hours`
            WHERE
                `location_id`='{locations_id}'
        """
        location = await helperdao.fetchone_dict(location_query)
        if location and location.get('is_all_time_available'):
            location["location_id"] = location.pop("id")
            location["day"] = {
                "is_open": True,
                "day": day,
                "from_time": str(time(0, 0, 0)),
                "to_time": str(time(23, 59, 59)),
            }
        else:
            location["location_id"] = location.pop("id")
            day_res = await helperdao.fetchone_dict(day_query)
            location["day"] = {
                "is_open": day_res.pop("is_open"),
                "day": day_res.pop("day"),
                "from_time": str(day_res.pop("from_time")),
                "to_time": str(day_res.pop("to_time")),
            }
        location.pop('created_at')
        location.pop('updated_at')
        return location
    except Exception as e:
        raise MySQLError(str(e))


async def get_location_amenities(locations_id, tenant_id):
    try:
        query = f"""
            Select la.location_id, a.label, a.icon
            FROM `tenant{tenant_id}`.`location_amenities` la
            LEFT JOIN `tenant{tenant_id}`.`amenities` a
            ON a.id = la.amenities_id WHERE la.location_id='{locations_id}'
        """
        amenities = await helperdao.fetchall_dict(query)
        return amenities if amenities else []
    except Exception as e:
        raise MySQLError(str(e))


async def get_location_images(locations_id, tenant_id):
    try:
        query = f"""
            Select location_id, image_url
            FROM location_images
            WHERE location_id='{locations_id}'
        """
        res = await helperdao.fetchall_dict(query)
        return res if res else []
    except Exception as e:
        raise MySQLError(str(e))


async def get_user_price_for_charger(user_id, charger_id, connector_id, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`customer_invites` civ
        INNER JOIN `tenant{tenant_id}`.`customer_connectors` up ON
            civ.id = up.customer_invite_id
        INNER JOIN `tenant{tenant_id}`.`charging_plans` pp ON
            up.charging_plan_id = pp.id
        INNER JOIN `tenant{tenant_id}`.`connectors` co ON
            co.charger_id = `up`.`charger_id`
        WHERE
            `civ`.`user_id` = '{user_id}'
        AND `up`.`charger_id` = '{charger_id}'
        AND `co`.`connector_id` = '{connector_id}'
        AND `up`.`deleted_at` is NULL;
    """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def get_organisation_of_user(user_id):
    query = f"""
        SELECT
            o.org_name,
            op.*
        FROM
            users u
        INNER JOIN organisations o ON
            o.org_id = u.org_id
        INNER JOIN organisation_properties op ON
            op.org_id = o.org_id
        WHERE
            u.user_id = '{user_id}';
    """
    res = await helperdao.fetchall_dict(query=query)
    if res:
        dict = {item["parameter_key"]: item["parameter_value"] for item in res}
        dict["org_name"] = res[0]["org_name"]
        return dict
    return {}


async def get_user(user_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`customer_invites`"
        if business_mobile_app
        else "`customer_invites`"
    )
    get_query = f"""
        SELECT
            *
        FROM
            {table}
        WHERE
            `user_id` = '{user_id}'
    """
    res = await helperdao.fetchone_dict(query=get_query)
    return res


async def delete_user(user_id, tenant_id, db_index, business_mobile_app):
    delete_string = f"deleted_user_{db_index}"
    table = (
        f"`tenant{tenant_id}`.`customer_invites`"
        if business_mobile_app
        else "`customer_invites`"
    )
    update_query = f"""
        UPDATE
            {table}
        SET
            `email` = '{delete_string}',
            `name` = '{delete_string}',
            `phone` = '{delete_string}'
        WHERE
            `user_id` = '{user_id}';
    """
    await helperdao.upsert_delete(query=update_query)


async def get_price_plan_by_session_parameter(session_id, tenant_id):
    query = f"""
        SELECT
            `pp`.*,
            `sp`.*
        FROM
            `tenant{tenant_id}`.`charging_plans` pp
        INNER JOIN `tenant{tenant_id}`.`session_parameters` sp ON
            pp.id = sp.charging_plan_id
        WHERE
            `sp`.`session_id` = '{session_id}';
    """
    res = await helperdao.fetchone_dict(query=query)
    return res


async def get_location_connectors_status(location_id: str, tenant_id: str):
    statuses = []
    try:
        query = f"""
            SELECT
                co.status
            FROM
                `tenant{tenant_id}`.`chargers` c
            INNER JOIN
                `tenant{tenant_id}`.`connectors` co
            ON
                co.charger_id = c.charger_id
            WHERE c.location_id={location_id}
        """
        res = await helperdao.fetchall_dict(query)
        for r in res:
            statuses.append(r["status"])
        return statuses
    except Exception as e:
        raise MySQLError(str(e))


async def get_notification_config(charger_type, user_id, tenant_id):
    try:
        query = f"""
            SELECT
                `notification_type`,
                `notification_value`
            FROM
                `tenant{tenant_id}`.`notification_config`
            WHERE
                `charger_type` = '{charger_type}' AND
                `user_id` = '{user_id}'
        """
        res = await helperdao.fetchone_dict(query)
        return res
    except Exception as e:
        raise MySQLError(str(e))


async def upsert_notification_config(
    charger_type, user_id, notification_type, notification_value, tenant_id
):
    try:
        config_exist = await get_notification_config(
            charger_type=charger_type, user_id=user_id, tenant_id=tenant_id
        )
        if not config_exist:
            query = f"""
                INSERT INTO `tenant{tenant_id}`.`notification_config`(
                    `user_id`,
                    `notification_type`,
                    `notification_value`,
                    `charger_type`
                )
                VALUES(
                    '{user_id}',
                    '{notification_type}',
                    '{notification_value}',
                    '{charger_type}'
                )
            """
        else:
            query = f"""
                UPDATE
                    `tenant{tenant_id}`.`notification_config`
                SET
                    `notification_type` = '{notification_type}',
                    `notification_value` = '{notification_value}'
                WHERE
                    `user_id` = '{user_id}'
                AND `charger_type` = '{charger_type}'
            """
        await helperdao.upsert_delete(query=query)
        return {"msg": "Notification settings are updated successfully."}
    except Exception as e:
        raise MySQLError(str(e))


async def get_users_private_plan(user_id, connector_id, charger_id, tenant_id):
    try:
        query = f"""
            SELECT
                pp.price,
                pp.billing_type AS bill_by
            FROM
                `tenant{tenant_id}`.`customer_invites` civ
            INNER JOIN `tenant{tenant_id}`.`customer_connectors` up
                ON civ.id=up.customer_invite_id
            INNER JOIN `tenant{tenant_id}`.`charging_plans` pp
                ON up.charging_plan_id = pp.id
            WHERE
                civ.user_id = '{user_id}'
            AND up.charger_id = '{charger_id}'
            AND up.connector_id = '{connector_id}';
        """
        res = await helperdao.fetchone_dict(query)
        return res
    except Exception as e:
        raise MySQLError(str(e))


async def update_phonepe_payment_status(
    success: bool,
    code: str,
    message: str,
    merchantId: str,
    merchantTransactionId: str,
    amount: int,
    phonepeTransactionId: str,
    data: str,
    state: str,
):
    try:
        query = f"""
        UPDATE `phonepe_transactions`
        SET phonepeTransactionId='{phonepeTransactionId}',
            success={success},
            code='{code}',
            message='{message}',
            data='{data}',
            amount='{amount}',
            merchantId='{merchantId}',
            state='{state}'
        WHERE `merchantTransactionId` = '{merchantTransactionId}'
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def get_coupon_details(tenant_id, offer_code=0, offer_id=0):
    try:
        if offer_code:
            query = f"""
                SELECT
                    *
                FROM
                    `tenant{tenant_id}`.`offers`
                WHERE offer_code='{offer_code}';
            """
        elif offer_id:
            query = f"""
                SELECT
                    *
                FROM
                    `tenant{tenant_id}`.`offers`
                WHERE offer_id='{offer_id}';
            """
        if query:
            res = await helperdao.fetchone_dict(query)
            return res
        else:
            return {}
    except Exception as e:
        raise MySQLError(str(e))


async def insert_user_redeem_details(user_id, offer_id, cashback_amount, tenant_id):
    query = f"""
        INSERT INTO
            `tenant{tenant_id}`.`offer_redeem_details`(
                user_id,
                offer_id,
                cashback_amount
            )
        VALUES(
            '{user_id}',
            '{offer_id}',
            '{cashback_amount}'
        )
    """
    res = await helperdao.upsert_delete(query=query)
    return res


async def get_user_limit_on_coupon(offer_id, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`offer_redeem_details`
        WHERE `offer_id`='{offer_id}'
    """
    res = await helperdao.fetchall_dict(query)
    return res


async def get_max_uses_per_user(user_id, offer_id, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`offer_redeem_details`
        WHERE
            `user_id` = '{user_id}'
        AND `offer_id`='{offer_id}';
    """
    res = await helperdao.fetchall_dict(query)
    return res


async def get_coupon_access_details(offer_id, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`offer_users`
        WHERE `offer_id`='{offer_id}'
    """
    res = await helperdao.fetchall_dict(query)
    return res


async def apply_coupon(user_id, offer_code, tenant_id):
    try:
        offer_details = await get_coupon_details(
            offer_code=offer_code,
            tenant_id=tenant_id,
        )
        if not offer_details:
            return {"msg": "Invalid offer code", "status": "Failed"}
        offer_id = offer_details.get("offer_id")
        coupon_access_list = await get_coupon_access_details(
            offer_id=offer_id,
            tenant_id=tenant_id,
        )
        user_have_access = False
        if not coupon_access_list:
            user_have_access = False
        else:
            if len(coupon_access_list) == 1:
                accessed_user_id = coupon_access_list[0]["user_id"]
                if accessed_user_id == "-1":
                    user_have_access = True
                elif accessed_user_id != "-1" and accessed_user_id != user_id:
                    user_have_access = False
            else:
                for user in coupon_access_list:
                    if user["user_id"] == user_id:
                        user_have_access = True
        if user_have_access is False:
            return {
                "msg": "User is not Authorized to use this coupon",
                "status": "Failed",
            }

        user_limit_on_coupon = offer_details.get("user_limit_on_coupon")
        max_uses_per_user = offer_details.get("max_uses_per_user")
        if str(user_limit_on_coupon) != "-1":
            offer_redeemed_details = await get_user_limit_on_coupon(
                offer_id=offer_id,
                tenant_id=tenant_id,
            )
            if len(offer_redeemed_details) >= int(user_limit_on_coupon):
                return {"msg": "offer limit is reached", "status": "Failed"}
        if str(max_uses_per_user) != "-1":
            redeem_time_by_user = await get_max_uses_per_user(
                user_id=user_id,
                offer_id=offer_id,
                tenant_id=tenant_id,
            )
            if len(redeem_time_by_user) >= int(max_uses_per_user):
                return {"msg": "max users per user limit reached.", "status": "Failed"}
        business_mobile_app = await does_business_have_mobile_app(tenant_id)
        user_wallet_details = await get_wallet_balance(
            user_id=user_id,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )
        before_user_wallet = user_wallet_details.get("wallet_balance")
        cashback_amount = offer_details.get("cashback_amount")
        after_user_wallet = round(before_user_wallet + cashback_amount, 2)
        await update_wallet_balance(
            user_id=user_id,
            new_balance=after_user_wallet,
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app
        )
        await insert_user_redeem_details(
            user_id=user_id,
            offer_id=offer_id,
            cashback_amount=cashback_amount,
            tenant_id=tenant_id
        )
        return {
            "status": "Success",
            "msg": "Coupon applied successfully",
            "before_user_wallet": before_user_wallet,
            "cashback_amount": cashback_amount,
            "after_user_wallet": after_user_wallet,
        }

    except Exception as e:
        raise MySQLError(str(e))


async def insert_merchant_transaction_id(user_id, merchant_transaction_id, tenant_id):
    try:
        query = f"""
        INSERT INTO `tenant{tenant_id}`.`phonepe_transactions`(
            `merchantTransactionId`,
            `userId`
        )
        VALUES(
            '{merchant_transaction_id}',
            '{user_id}'
        )
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def get_user_id_from_merchant_transaction_id(merchant_transaction_id):
    try:
        query = f"""
        SELECT `userId` FROM `phonepe_transactions` WHERE
        merchantTransactionid = '{merchant_transaction_id}'
        """
        if query:
            res = await helperdao.fetchone_dict(query)
            return res
        else:
            return {}
    except Exception as e:
        raise MySQLError(str(e))


async def update_phonepe_transaction(
    merchant_id: str, merchant_transaction_id: str, amount: int, tenant_id: str
):
    try:
        query = f"""
            UPDATE `tenant{tenant_id}`.`phonepe_transactions`
            SET `merchantId`='{merchant_id}', `amount`='{amount}'
            WHERE `merchantTransactionId`='{merchant_transaction_id}'
        """
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def get_location_org_id_by_charger_id(charger_id):
    query = f"""
        select l.org_id from locations l inner join chargers c
        on l.id=c.location_id where c.charger_id='{charger_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def is_session_running_v2(session_id: str, tenant_id: str):
    query = f"""
        select id, start_id_tag, start_time from
        `tenant{tenant_id}`.`sessions` where
        id={session_id} and is_running=1;
    """
    res = await helperdao.fetchone(query)
    if res is not None:
        return True, res[1], res[2]
    return False, None, None


async def enterprise_id_tags(user_id):
    query_for_enterprise = f"""
    SELECT
        rfid_number as id_tag
    FROM
        `rfid_cards`
    WHERE
        user_id='{user_id}'
    """
    res = await helperdao.fetchall_dict(query=query_for_enterprise)
    return [x.get("id_tag") for x in res] if res else []


async def get_id_tags_by_user_id(user_id, tenant_id):
    id_tags = {tenant_id: []}
    query_for_tenant = f"""
    SELECT
        rfid_number as id_tag
    FROM
        `tenant{tenant_id}`.`rfid_cards`
    WHERE
        user_id='{user_id}'
    """

    cards = await helperdao.fetchall_dict(query=query_for_tenant)

    for card in cards:
        id_tags[tenant_id].append(card.get('id_tag'))

    return id_tags


async def get_all_running_session_by_id_tags(id_tags, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`sessions`
        WHERE
            start_id_tag IN ('{id_tags}')
        AND
            is_running=1;
    """
    res = await helperdao.fetchall_dict(query)
    return res


async def get_session_detail_by_id(session_id, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`sessions`
        WHERE
            id='{session_id}';
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def get_connector_detail(charger_id, connector_id, tenant_id):
    query = f"""
        SELECT * FROM `tenant{tenant_id}`.`connectors`
        WHERE `charger_id`='{charger_id}' AND
        `connector_id`='{connector_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def get_charger_and_user_details_by_session_id(session_id):
    query = f"""
        SELECT
            s.charger_id,
            s.connector_id,
            sd.vehicle_id,
            rc.user_id
        FROM
            sessions s
        INNER JOIN session_duration sd ON
            s.id = sd.session_id
        INNER JOIN rfid_cards rc ON
            rc.id_tag = sd.id_tag
        INNER JOIN charger_details c ON
            c.charger_id = s.charger_id
        WHERE
            s.id = {session_id};
    """
    res = await helperdao.fetchone_dict(query)
    if res:
        vehicle_id = res.get("vehicle_id")
        user_id = res.get("user_id")
        connector_id = res.get("connector_id")
        charger_id = res.get("charger_id")
        data = await get_session_details(session_id, charger_id, connector_id)
        data.update({"is_charging_stopped": True})
        charging_cost = data["invoice"]["charging_cost"]
        tax_percent = data["invoice"]["tax_percent"]
        charging_cost_with_tax = data["invoice"]["charging_cost_with_tax"]
        id = await insert_public_charging_session_details(
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
        return data
    return None


async def get_old_meter_values(session_id, limit=5):
    query = f"""
        SELECT * FROM `sessions_meter_values`
        WHERE session_id='{session_id}' ORDER BY id DESC LIMIT {limit};
    """
    res = await helperdao.fetchall_dict(query)
    return res if res else []


async def insert_idle_fee(session_id, idle_charging_cost, idle_minutes, idle_price):
    try:
        query = f"""
            UPDATE
                `invoice`
            SET
                `idle_minutes` = '{idle_minutes}',
                `idle_price` = '{idle_price}',
                `idle_charging_cost` = '{idle_charging_cost}'
            WHERE
                `session_id` = '{session_id}'
        """
        res = await helperdao.upsert_delete(query)
        return res
    except Exception as e:
        raise MySQLError(str(e))


async def get_user_id_by_session_id(session_id):
    query = f"""
        SELECT r.user_id FROM sessions s inner join rfid_cards r
        on s.start_id_tag=r.id_tag WHERE s.id='{session_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return res.get("user_id") if res else None


async def get_ongoing_idle_sessions(user_id, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`business_transactions` i
        INNER JOIN
            `tenant{tenant_id}`.`connectors` cc
        ON
            i.charger_id=cc.charger_id
        WHERE
            cc.status='Finishing' AND
            i.user_id='{user_id}'
        ORDER BY
            i.id
        DESC;
    """
    res = await helperdao.fetchall_dict(query)
    session_ids = []
    unique_combinations = set()
    for session in res:
        charger_id = session["charger_id"]
        connector_id = session["connector_id"]
        session_id = session["session_id"]
        combination = (charger_id, connector_id)
        if combination not in unique_combinations:
            unique_combinations.add(combination)
            session_ids.append(session_id)
    return {tenant_id: session_ids}


async def get_location_charger_details(charger_id, connector_id, tenant_id):
    query = f"""
        SELECT
            *
        FROM
            `tenant{tenant_id}`.`chargers` C
        INNER JOIN
            `tenant{tenant_id}`.`locations` L
        ON
            C.location_id=L.id
        INNER JOIN
            `tenant{tenant_id}`.`connectors` CC
        ON C.charger_id=CC.charger_id
        WHERE
            C.charger_id='{charger_id}'
        AND CC.connector_id='{connector_id}';
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def delete_notification_config(user_id, charger_type, tenant_id):
    query = f"""
        DELETE FROM
            `tenant{tenant_id}`.`notification_config`
        WHERE
            `user_id`='{user_id}'
        AND `charger_type`='{charger_type}'
    """
    await helperdao.upsert_delete(query)
    return {"msg": "Notification settings are removed."}


async def get_stripe_cust_id(user_id):
    query = f"""
        SELECT * FROM `stripe_customers` WHERE `user_id`='{user_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def insert_stripe_customer(user_id, cust_id):
    query = f"""
        INSERT INTO `stripe_customers`(`user_id`, `cust_id`)
        VALUES ('{user_id}','{cust_id}')
    """
    await helperdao.upsert_delete(query)
    return


async def get_holding_amount(charger_type=None, org_id=None, org_ids=None):
    if org_id:
        query = f"""
            SELECT * FROM `organisation_holding_charges`
            WHERE `org_id`='{org_id}'
        """
        if charger_type:
            query += f" AND `charger_type`='{charger_type}'"
        res = await helperdao.fetchone_dict(query)
        return res if res else {}
    elif org_ids:
        query = f"""
            SELECT * FROM `organisation_holding_charges`
            WHERE `org_id` IN ('{org_ids}')
        """
        res = await helperdao.fetchall_dict(query)
        return res if res else []


async def charger_detail(charger_id: str, tenant_id: str):
    table = (
        f"`tenant{tenant_id}`.`chargers`"
    )
    query = f"""
        SELECT
            *
        FROM
            {table}
        WHERE
        charger_id='{charger_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def insert_payment_intent_info(
    payment_intent_id,
    payment_method_id,
    charger_id,
    connector_id,
    user_id,
    amount,
    currency,
    cust_id,
):
    query = f"""
        INSERT INTO `holding_cards_payment_intents`(
        `payment_intent_id`, `payment_method_id`, `charger_id`, `connector_id`,
        `user_id`, `amount`, `currency`, `cust_id`) VALUES ('{payment_intent_id}',
        '{payment_method_id}', '{charger_id}','{connector_id}',
        '{user_id}','{amount}','{currency}', '{cust_id}')
    """
    return await helperdao.upsert_delete(query)


async def insert_stripe_transaction_info(
    payment_intent_id,
    max_amount,
    amount_captured,
    amount_refunded,
    txn_charge_id,
    currency,
    cust_id,
    receipt_url,
    status,
):
    query = f"""
        INSERT INTO `holding_cards_payment_status`(
            `payment_intent_id`,
            `max_amount`,
            `amount_captured`,
            `amount_refunded`,
            `txn_charge_id`,
            `currency`,
            `cust_id`,
            `receipt_url`,
            `status`
        )
        VALUES(
            '{payment_intent_id}',
            '{max_amount}',
            '{amount_captured}',
            '{amount_refunded}',
            '{txn_charge_id}',
            '{currency}',
            '{cust_id}',
            '{receipt_url}',
            '{status}'
        )
    """
    await helperdao.upsert_delete(query)
    return


async def get_latest_payment_intent_id(charger_id, connector_id, user_id, tenant_id):
    query = f"""
        SELECT * FROM `tenant{tenant_id}`.`holding_cards_payment_intents` WHERE
        `charger_id`='{charger_id}' AND `connector_id`='{connector_id}'
        AND `user_id`='{user_id}' order by id desc;
    """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def insert_session_payment_intent_mapping(session_id, payment_intent_id):
    query = f"""
        INSERT INTO `session_payment_method`(`session_id`,
        `payment_intent_id`) VALUES ('{session_id}','{payment_intent_id}')
    """
    return await helperdao.upsert_delete(query)


async def get_payment_intent_id(session_id):
    query = f"""
        SELECT `payment_intent_id` FROM `session_payment_method`
        WHERE `session_id`='{session_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def get_payment_intent_detail(payment_intent_id):
    query = f"""
        SELECT * FROM `holding_cards_payment_intents` WHERE
        `payment_intent_id`='{payment_intent_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return res


async def get_card_logos():
    query = """
        SELECT name, logo_url FROM `card_logos`;
    """
    res = await helperdao.fetchall(query)
    res = dict(res) if res else {}
    return res


async def check_and_get_if_user_authorize_on_charger(user_id, charger_id=""):
    query = f"""
        SELECT * FROM `chargers_price_group` cpg INNER JOIN
        `group_users` gu on cpg.group_id=gu.group_id WHERE
        gu.user_id='{user_id}'
    """
    if charger_id:
        query = f" AND cpg.charger_id='{charger_id}'"
        res = await helperdao.fetchone_dict(query)
        return res if res else {}
    else:
        res = await helperdao.fetchall_dict(query)
        return res if res else []


async def get_plugshare_link(charger_id: str, tenant_id: str):
    query = f"""
        SELECT
            `link`
        FROM
            `tenant{tenant_id}`.`plugshare_links`
        WHERE
            `charger_id`= '{charger_id}'
    """
    res = await helperdao.fetchone_dict(query=query)
    return res.get("link") if res else ""


async def get_price_plan_of_user(user_id, charger_id, connector_id, tenant_id):
    try:
        plan_id = 0
        plan_id = await check_user_have_private_plans(
            user_id=user_id,
            charger_id=charger_id,
            connector_id=connector_id,
            tenant_id=tenant_id,
        )

        if not plan_id:
            plan_id = await get_charging_plan_of_connector(
                charger_id=charger_id,
                connector_id=connector_id,
                tenant_id=tenant_id,
            )

        if not plan_id:
            plan_id = await get_charging_plan_of_location(
                charger_id=charger_id,
                tenant_id=tenant_id,
            )

        utils.check_object_existence(plan_id, "Price Plan")

        price_detail = await get_pricing_plan(
            price_id=plan_id,
            tenant_id=tenant_id,
        )

        utils.check_object_existence(price_detail, "Price Plan")

        return price_detail

    except MissingObjectOnDB as e:
        raise e

    except Exception as e:
        raise e


async def insert_payment_transaction(merchantPaymentId, currency, amount, transactionTime, user_id, tenant_id, paymentGateway, status):
    if (tenant_id != "enterprise"):
        query = f"""
            INSERT into `tenant{tenant_id}`.`payment_transactions`
            (merchantPaymentId, currency, amount, transactionTime, user_id, paymentGateway, status)
            VALUES
            ('{merchantPaymentId}', '{currency}', '{amount}', '{transactionTime}', '{user_id}', '{paymentGateway}', '{status}');
        """
    else:
        query = f"""
            INSERT into `payment_transactions`
            (merchantPaymentId, currency, amount, transactionTime, user_id, paymentGateway)
            VALUES
            ('{merchantPaymentId}', '{currency}', '{amount}', '{transactionTime}', '{user_id}', '{paymentGateway}', '{status}');
        """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def update_payzone_transaction(status, merchantPaymentId,
                                     paymentGatewayPaymentId,
                                     paymentType,
                                     paymentMethod,
                                     data,
                                     tenant_id):
    if (tenant_id != "enterprise"):
        query = f"""
            UPDATE `tenant{tenant_id}`.`payment_transactions`
            SET `status`='{status}', `paymentGatewayPaymentId`='{paymentGatewayPaymentId}',
            `paymentType`='{paymentType}', `paymentMethod`='{paymentMethod}', `data`='{str(data)}'
            WHERE `merchantPaymentId`='{merchantPaymentId}'
        """
    else:
        query = f"""
            UPDATE `payment_transactions`
            SET `status`='{status}', `paymentGatewayPaymentId`='{paymentGatewayPaymentId}',
            `paymentType`='{paymentType}', `paymentMethod`='{paymentMethod}', `data`='{str(data)}'
            WHERE `merchantPaymentId`='{merchantPaymentId}'
        """
    res = await helperdao.upsert_delete(query)
    return res if res else {}


async def get_user_id_for_payzone_transaction(merchantPaymentId, tenant_id):
    if (tenant_id != "enterprise"):

        query = f"""
            SELECT
                `user_id`
            FROM
                `tenant{tenant_id}`.`payment_transactions`
            WHERE
                `merchantPaymentId`= '{merchantPaymentId}'
        """
    else:
        query = f"""
            SELECT
                `user_id`
            FROM
                `payment_transactions`
            WHERE
                `merchantPaymentId`= '{merchantPaymentId}'
        """
    res = await helperdao.fetchone_dict(query=query)
    return res.get("user_id") if res else ""
