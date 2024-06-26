from __future__ import annotations
from datetime import datetime, time

import logging

from dao import helperdao
from errors.mysql_error import MySQLError


LOGGER = logging.getLogger("server")


async def get_logo_of_third_party_charger() -> dict:
    query = """
        SELECT name, logo_url FROM charger_networks;
    """
    res = await helperdao.fetchall(query)
    return {} if not res else dict(res)


async def get_all_charging_stations(
    org_ids=None,
    locations_ids=[],
    authorized_charger_list=[],
) -> dict:
    if locations_ids is None:
        locations_ids = []
    try:
        query = """
            SELECT
                c.id,
                c.brand,
                c.model,
                c.is_third_party_charger,
                c.third_party_brand_name,
                pp.price,
                pp.billing_type,
                c.public,
                c.temp_closed,
                c.hide_on_map,
                co.charger_id,
                co.connector_id,
                co.max_output,
                co.type,
                co.status,
                co.availability,
                c.location_id,
                c.charger_name as charger_name
            FROM
                charger_details c
            INNER JOIN charger_connector_details co ON
                co.charger_id = c.id
            INNER JOIN price_plans pp ON
                c.price_id = pp.price_id
            INNER JOIN locations l ON
                c.location_id = l.id
            WHERE
                c.hide_on_map = 0
        """
        if org_ids:
            query += f" AND l.org_id IN ('{org_ids}')"
        if locations_ids:
            locations_list_str = ("','").join([str(x) for x in locations_ids])
            query += f" AND c.location_id IN ('{locations_list_str}')"
        res = await helperdao.fetchall_dict(query)
        chargers_dict = {}
        brand_logo_dict = await get_logo_of_third_party_charger()
        if res is not None:
            for row in res:
                if chargers_dict.get(row["id"]):
                    chargers_dict[row["id"]]["connectors"].append(
                        {
                            "connector_id": row["connector_id"],
                            "max_output": row["max_output"],
                            "type": row["co.type"],
                            "status": row["status"],
                            "availability": row["availability"],
                        },
                    )
                elif row["public"] == 1 or (
                    authorized_charger_list and (
                        row["id"] in authorized_charger_list)
                ):
                    chargers_dict[row["id"]] = {
                        "charger_id": row["id"],
                        "charger_name": row["charger_name"],
                        "serial_number": row["serial_number"],
                        "model": row["model"],
                        "type": row["type"],
                        "is_third_party_charger": row["is_third_party_charger"],
                        "third_party_brand_name": row["third_party_brand_name"],
                        "third_party_brand_logo": brand_logo_dict.get(
                            row["third_party_brand_name"],
                            "https://dummpy.logo",
                        ),
                        "price": row["price"],
                        "bill_by": row["billing_type"],
                        "public": row["public"],
                        "temp_closed": row["temp_closed"],
                        "hide_on_map": row["hide_on_map"],
                        "location_id": row["location_id"],
                        "show_name_on_app": row["show_name_on_app"],
                        "org_id": row["org_id"],
                        "connectors": [
                            {
                                "connector_id": row["connector_id"],
                                "max_output": row["max_output"],
                                "type": row["co.type"],
                                "status": row["status"]
                                if not row["is_third_party_charger"]
                                else "N/A",
                                "availability": row["availability"],
                            },
                        ],
                    }
        return chargers_dict
    except Exception as e:
        raise MySQLError(str(e))


async def get_third_party_chargers(org_ids):
    try:
        query = f"""
            SELECT
                c.charger_id,
                co.charger_id,
                co.connector_id,
                co.max_output,
                co.type as connector_type,
                c.location_id,
                c.third_party_brand_name,
                cn.logo_url,
                l.org_id
            FROM
                third_party_chargers c
            INNER JOIN third_party_charger_connectors co ON
                co.charger_id = c.charger_id
            INNER JOIN third_party_locations l ON
                c.location_id = l.id
            INNER JOIN charger_networks cn ON
                cn.name=c.third_party_brand_name
            WHERE
                l.org_id IN ('{org_ids}')
            limit 1000
        """
        res = await helperdao.fetchall_dict(query)
        chargers_dict = {}
        if res is not None:
            for row in res:
                if chargers_dict.get(row["charger_id"]):
                    chargers_dict[row["charger_id"]]["connectors"].append(
                        {
                            "connector_id": row["connector_id"],
                            "max_output": row["max_output"],
                            "type": row["connector_type"],
                            "status": "N/A",
                            "availability": "",
                        },
                    )
                else:
                    chargers_dict[row["charger_id"]] = {
                        "charger_id": row["charger_id"],
                        "charger_name": row["charger_id"],
                        "serial_number": row["charger_id"],
                        "model": row["charger_id"],
                        "type": row["type"],
                        "price": "",
                        "bill_by": "",
                        "public": 1,
                        "temp_closed": 0,
                        "hide_on_map": 0,
                        "location_id": row["location_id"],
                        "show_name_on_app": 0,
                        "org_id": row["org_id"],
                        "is_third_party_charger": 1,
                        "third_party_brand_logo": row["logo_url"],
                        "third_party_brand_name": row["third_party_brand_name"],
                        "connectors": [
                            {
                                "connector_id": row["connector_id"],
                                "max_output": row["max_output"],
                                "type": row["connector_type"],
                                "status": "N/A",
                                "availability": "",
                            },
                        ],
                    }
        return chargers_dict
    except Exception as e:
        raise MySQLError(str(e))


async def get_all_charging_locations(locations_ids: list, day: str):
    try:
        from utils import format_time_with_leading_zeros
        locations_list_str = (
            (",").join([str(x)
                        for x in locations_ids]) if locations_ids else "0"
        )
        query = f"""
            Select l.id, l.label as name, l.address_line_1 as address1, l.geo_coordinates,
            a.is_open, a.day, a.start_time as from_time, a.end_time as to_time
            FROM locations l INNER JOIN active_hours a on a.location_id = l.id
            WHERE l.id IN ({locations_list_str}) and a.day = '{day}' and l.deleted_at is NULL
        """
        res = await helperdao.fetchall_dict(query)
        locations = {}
        if res is not None:
            for row in res:
                row["from_time"] = format_time_with_leading_zeros(
                    row["from_time"])
                row["to_time"] = format_time_with_leading_zeros(row["to_time"])
                locations[row["id"]] = row
        return locations
    except Exception as e:
        raise LOGGER.error(str(e))


async def get_all_third_party_charging_locations(locations_ids, day):
    try:
        locations_list_str = (
            (",").join([str(x)
                        for x in locations_ids]) if locations_ids else "0"
        )
        query = f"""
            Select
                l.id,
                l.label as name,
                l.phone,
                l.address as address1,
                l.geo_coordinates
            FROM
                third_party_locations l
            WHERE
                l.id IN ({locations_list_str});
        """
        print(query)
        res = await helperdao.fetchall_dict(query)
        locations = {}
        if res:
            for row in res:
                row["from_time"] = "00:00:00"
                row["to_time"] = "23:59:59"
                locations[row["id"]] = row
        return locations

    except Exception as e:
        LOGGER.error(e)


async def get_location_amenities(locations_ids: list):
    try:
        locations_list_str = (
            (",").join([str(x)
                        for x in locations_ids]) if locations_ids else "0"
        )
        query = f"""
            Select la.location_id, a.label, a.icon
            FROM location_amenities la LEFT JOIN amenities a ON a.id = la.amenities_id
            WHERE la.location_id IN ({locations_list_str})
        """
        res = await helperdao.fetchall_dict(query)
        amenities = {}
        if res is not None:
            for row in res:
                if amenities.get(row["location_id"]):
                    amenities[row["location_id"]].append(row)
                else:
                    amenities[row["location_id"]] = []
                    amenities[row["location_id"]].append(row)
        return amenities
    except Exception as e:
        raise MySQLError(str(e))


async def get_location_images(locations_ids: list):
    try:
        locations_list_str = (
            (",").join([str(x)
                        for x in locations_ids]) if locations_ids else "0"
        )
        query = f"""
            Select location_id, image_url
            FROM location_images
            WHERE location_id IN ({locations_list_str})
        """
        res = await helperdao.fetchall_dict(query)
        images = {}
        if res is not None:
            for row in res:
                if images.get(row["location_id"]):
                    images[row["location_id"]].append(row)
                else:
                    images[row["location_id"]] = []
                    images[row["location_id"]].append(row)
        return images
    except Exception as e:
        raise MySQLError(str(e))


async def get_location_active_hours(locations_ids: list):
    try:
        locations_list_str = ""
        if len(locations_ids) > 0:
            output = [str(x) for x in locations_ids]
            locations_list_str = (",").join(output)
            # locations_list_str = locations_
            # list_str[:-1]

        query = f"""
            Select location_id, image_url
            FROM location_images
            WHERE location_id IN ({locations_list_str})
        """
        res = await helperdao.fetchall_dict(query)
        images = {}
        if res is not None:
            for row in res:
                if images.get(row["location_id"]):
                    images[row["location_id"]].append(row)
                else:
                    images[row["location_id"]] = []
                    images[row["location_id"]].append(row)
        return images
    except Exception as e:
        raise MySQLError(str(e))


async def get_connector_list(tenant_id):
    try:
        query = f"""
            SELECT
                DISTINCT(`type`)
            FROM
                `tenant{tenant_id}`.`connectors`;
        """
        res = await helperdao.fetchall_dict(query)
        return [connector.get("type") for connector in res] if res is not None else []
    except Exception as e:
        raise MySQLError(str(e))


async def get_user_price_for_chargers(user_id):
    query = f"""
        SELECT
            *
        FROM
            `user_price` up
        INNER JOIN `price_plans` pp ON
            up.price_id = pp.price_id
        WHERE
            `up`.`user_id` = '{user_id}';
    """
    res = await helperdao.fetchall_dict(query)
    return res


async def get_all_child_businesses():
    query = """
        SELECT * FROM `businesses` WHERE `have_mobile_app`='0' and tenant_id is not null;
    """
    res = await helperdao.fetchall_dict(query)
    return res


async def get_group_plans(user_id, charger_id=0):
    query = f"""
        SELECT cpg.charger_id, pp.price_id, pp.price, pp.billing_type, pp.plan_type FROM
        `group_users` gu INNER JOIN `chargers_price_group` cpg ON
        gu.group_id=cpg.group_id INNER JOIN price_plans pp ON cpg.price_id=pp.price_id
        WHERE gu.user_id='{user_id}'
    """
    if charger_id:
        query += f' AND cpg.charger_id="{charger_id}"'
    return await helperdao.fetchall_dict(query)


async def get_organisation_faq(tenant_id: str) -> list:
    query = f"""
        SELECT `id`, `org_id`, `question`, `answer` FROM
        `tenant{tenant_id}``faq_organisations`
    """
    res = await helperdao.fetchall_dict(query)
    return res if res else []


async def does_business_have_mobile_app(tenant_id):
    query = f"""
        select * from businesses where tenant_id='{tenant_id}';
    """
    res = await helperdao.fetchone_dict(query)
    res = res if res else {}
    return bool(res.get("have_mobile_app", False))


async def get_business_settings(tenant_ids):
    query = f"""
        SELECT
            *
        FROM
            `business_settings` bs
        INNER JOIN `businesses` b
        ON bs.business_id=b.id
        WHERE
            `b`.`tenant_id` IN ('{tenant_ids}')
    """
    res = await helperdao.fetchall_dict(query)
    return {item.get("tenant_id"): item for item in res} if res else {}


async def get_tenants_properties(tenant):
    query = f"""
        SELECT
            bp.*
        FROM
            `business_properties` bp
        INNER JOIN `businesses` b
        ON
            b.id=bp.business_id
        WHERE
            `b`.`tenant_id` = '{tenant}';
    """
    res = await helperdao.fetchall_dict(query)
    return (
        {tenant: {i.get("property_key"): i.get("property_value") for i in res}}
        if res
        else {}
    )


async def get_enterprise_properties():
    query = """
        SELECT
            *
        FROM
            `enterprise_properties`;
    """
    res = await helperdao.fetchall_dict(query)
    properties = {}
    for property in res:
        key = property['property_key']
        value = property['property_value']
        properties[key] = value
    return properties


async def get_location_of_tenant(tenant, day, location_ids=""):
    from utils import format_time_object

    location_ids = (
        "', '".join([str(location) for location in location_ids])
        if location_ids
        else []
    )
    query = f"""
        SELECT
            l.`id`,
            l.`label`,
            l.`address_line_1`,
            l.`address_line_2`,
            l.`state`,
            l.`city`,
            l.`zip_code`,
            l.`geo_coordinates`,
            l.`restricted_area`,
            l.`is_all_time_available`
        FROM
            `tenant{tenant}`.`locations` l
        WHERE
            l.deleted_at is NULL
    """
    if location_ids:
        query += f"AND l.id IN '{location_ids}'"
    res = await helperdao.fetchall_dict(query)
    for location in res:
        is_all_time_available = location.get("is_all_time_available", True)
        if not is_all_time_available:
            location_hours_query = f"""
                SELECT
                    lh.`day`,
                    lh.`start_time` as from_time,
                    lh.`end_time` as to_time,
                    lh.`is_active` as is_open
                FROM
                    `tenant{tenant}`.`locations_hours` lh
                WHERE
                    lh.day='{day}' and lh.location_id='{location.get('id')}'
            """
            day_res = await helperdao.fetchone_dict(location_hours_query)
            location["is_open"] = day_res.get("is_open", False)
            from_time = datetime.strptime(str(day_res.get("from_time")), "%H:%M:%S").time(
            ) if day_res.get("from_time") else datetime.strptime("00:00:00", "%H:%M:%S").time()
            to_time = datetime.strptime(str(day_res.get("to_time")), "%H:%M:%S").time(
            ) if day_res.get("to_time") else datetime.strptime("23:59:59", "%H:%M:%S").time()
            location["from_time"] = format_time_object(from_time)
            location["to_time"] = format_time_object(to_time)
            location["day"] = day
        else:
            location["is_open"] = True
            location["from_time"] = format_time_object(datetime.strptime(
                "00:00:00", "%H:%M:%S").time())
            location["to_time"] = format_time_object(datetime.strptime(
                "23:59:59", "%H:%M:%S").time())
            location["day"] = day

    return {tenant: {i.get("id"): i for i in res}}


async def get_location_amenities_of_tenant(tenant, location_ids=""):
    location_ids = (
        "', '".join([str(location) for location in location_ids])
        if location_ids
        else []
    )
    query = f"""
        SELECT
            la.location_id,
            a.`id`,
            a.`label`,
            a.`icon`
        FROM
            `tenant{tenant}`.`location_amenities` la
        INNER JOIN
            `tenant{tenant}`.`amenities` a
        ON
            la.amenities_id=a.id
    """
    if location_ids:
        query += f"WHERE la.location_id IN ('{location_ids}')"
    res = await helperdao.fetchall_dict(query)
    amenities = {}
    for i in res:
        key = i.pop("location_id")
        if not amenities.get(key):
            amenities[key] = [i]
        else:
            amenities[key].append(i)
    return {tenant: amenities}


async def get_location_review_of_tenant(tenant, location_ids=""):
    location_ids = (
        "', '".join([str(location) for location in location_ids])
        if location_ids
        else []
    )
    query = f"""
        SELECT
            `location_id`,
            `to_id`,
            `from_id`,
            `star_rating`,
            `review`
        FROM
            `tenant{tenant}`.`location_reviews` lr
    """
    if location_ids:
        query += f"WHERE lr.location_id IN ('{location_ids}')"
    res = await helperdao.fetchall_dict(query)
    reviews = {}
    for i in res:
        if not reviews.get("location_id"):
            reviews[i.get("location_id")] = [i]
        else:
            reviews[i.get("location_id")].append(i)
    return {tenant: reviews}


async def get_location_chargers_of_tenant(tenant, location_ids=""):
    location_ids = (
        "', '".join([str(location) for location in location_ids])
        if location_ids
        else []
    )
    query = f"""
        SELECT
            `charger_id`,
            `charger_name`,
            `brand`,
            `model`,
            `status`,
            `availability`,
            `accessibility`,
            `max_output`,
            `location_id`
        FROM
            `tenant{tenant}`.`chargers` c
        WHERE c.deleted_at is null
    """
    if location_ids:
        query += f" AND c.location_id IN ('{location_ids}')"
    res = await helperdao.fetchall_dict(query)
    chargers = {}
    for i in res:
        location_id = i.get("location_id")
        if not chargers.get(location_id):
            chargers[location_id] = [i]
        else:
            chargers[location_id].append(i)
    return {tenant: chargers}


async def charger_connector_of_tenant(tenant, user_id, business_mobile_app):
    query = f"""
        SELECT
            c.location_id,
            cc.charger_id,
            cc.connector_id,
            cc.max_output,
            cc.type,
            cc.status,
            cc.availability,
            cc.note,
            cp.label,
            cp.type as plan_type,
            cp.billing_type,
            cp.price,
            cp.fixed_starting_fee,
            cp.idle_charging_fee,
            cp.apply_after
        FROM
            `tenant{tenant}`.`chargers` c
        INNER JOIN
            `tenant{tenant}`.`connectors` cc
        ON
            c.charger_id=cc.charger_id
        INNER JOIN
            `tenant{tenant}`.`charging_plans` cp
        ON
            cc.charging_plan_id=cp.id
        WHERE cc.deleted_at is NULL
    """
    res = await helperdao.fetchall_dict(query)
    private_plan = await get_user_private_charger_connectors(
        tenant=tenant, user_id=user_id, business_mobile_app=business_mobile_app
    )
    connectors = {}
    for i in res:
        location_id = i.pop('location_id')
        charger_id = i.pop('charger_id')
        connector_id = i.get('connector_id')
        private_connector = {}
        if private_plan.get(charger_id) and private_plan[charger_id].get(connector_id):
            private_connector = private_plan[charger_id][connector_id]
            i['label'] = private_connector.get('label', i.get('label'))
            i['plan_type'] = private_connector.get(
                'plan_type', i.get('plan_type'))
            i['billing_type'] = private_connector.get(
                'billing_type',
                i.get('billing_type')
            )
            i['apply_after'] = private_connector.get(
                'apply_after',
                i.get('apply_after')
            )
        i['price'] = float(private_connector.get('price', i.get('price')))
        i['idle_charging_fee'] = float(private_connector.get(
            'idle_charging_fee',
            i.get('idle_charging_fee')
        ))
        i['fixed_starting_fee'] = float(private_connector.get(
            'fixed_starting_fee',
            i.get('fixed_starting_fee')
        ))
        if connectors.get(location_id):
            if connectors[location_id].get(charger_id):
                connectors[location_id][charger_id].append(i)
            else:
                connectors[location_id][charger_id] = [i]
        else:
            connectors[location_id] = {charger_id: [i]}
    return {tenant: connectors}


async def get_user_private_charger_connectors(tenant, user_id, business_mobile_app):
    table = (
        f"`tenant{tenant}`.`customer_invites` ci"
        if business_mobile_app
        else "`customer_invites` ci"
    )
    query = f"""
        SELECT
            cc.charger_id,
            cc.connector_id,
            cp.label,
            cp.type as plan_type,
            cp.billing_type,
            cp.price,
            cp.fixed_starting_fee,
            cp.idle_charging_fee,
            cp.apply_after
        FROM
            {table}
        INNER JOIN
            `tenant{tenant}`.`customer_connectors` c
        ON ci.id=c.customer_invite_id
        INNER JOIN `tenant{tenant}`.`connectors` cc
            ON c.connector_row_id=cc.id
        INNER JOIN
            `tenant{tenant}`.`charging_plans` cp
        ON
            c.charging_plan_id=cp.id
        WHERE
            ci.user_id='{user_id}'
        AND
            c.deleted_at is NULL
    """
    res = await helperdao.fetchall_dict(query)
    connectors = {}
    for i in res:
        charger_id = i.get("charger_id")
        connector_id = i.get("connector_id")
        i["price"] = float(i.get("price", 0))
        i["idle_charging_fee"] = float(i.get("idle_charging_fee", 0))
        i["fixed_starting_fee"] = float(i.get("fixed_starting_fee", 0))
        if not connectors.get(charger_id):
            connectors[charger_id] = {connector_id: i}
        else:
            connectors[i.get("charger_id")].update({connector_id: i})
    return connectors


async def get_recent_charging_stations(user_id: str, tenant: str):
    try:
        location_ids = []
        query = f"""
            SELECT
                c.location_id,
                psd.session_start_time
            FROM
                `tenant{tenant}`.`business_transactions` psd
            INNER JOIN `tenant{tenant}`.`chargers` c ON
                psd.charger_id = c.charger_id
            WHERE
                psd.user_id='{user_id}'
            GROUP BY
                c.location_id
            ORDER BY
                psd.id DESC
            LIMIT 3;
        """
        res = await helperdao.fetchall_dict(query)
        if res:
            for location in res:
                location_ids.append(location)
        return {tenant: location_ids}
    except Exception as e:
        LOGGER.error(e)
        raise MySQLError(str(e))


async def get_user_login_session(user_id, business_mobile_app, tenant_id):
    table = (
        f"`tenant{tenant_id}`.`user_sessions`"
        if business_mobile_app
        else "`user_sessions`"
    )
    query = f"""
        SELECT
            `expiry_date`
        FROM
            {table}
        WHERE `user_id` = '{user_id}';
    """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def update_session_expiry_time(
    user_id,
    new_expiry_date,
    business_mobile_app,
    tenant_id
):
    table = (
        f"`tenant{tenant_id}`.`user_sessions`"
        if business_mobile_app
        else "`user_sessions`"
    )
    query = f"""
        UPDATE
            {table}
        SET
            `expiry_date`='{new_expiry_date}'
        WHERE `user_id`='{user_id}'
    """
    await helperdao.upsert_delete(query)
    return


async def insert_login_session_date(
    user_id,
    expiry_date,
    business_mobile_app,
    tenant_id
):
    table = (
        f"`tenant{tenant_id}`.`user_sessions`"
        if business_mobile_app
        else "`user_sessions`"
    )
    query = f"""
        INSERT INTO {table}(
            `user_id`,
            `expiry_date`
        ) VALUES (
            '{user_id}',
            '{expiry_date}'
        );
    """
    await helperdao.upsert_delete(query)
    return


async def set_role_of_new_user(user_id, business_mobile_app, tenant_id):
    table = (
        f"`tenant{tenant_id}`.`model_has_roles`"
        if business_mobile_app
        else "`model_has_roles`"
    )
    model = r"App\\Models\\User"
    query = f"""
        INSERT INTO {table}(
            `role_id`,
            `model_type`,
            `model_id`
        )
        VALUES
            ('4', '{model}', '{user_id}')
    """
    await helperdao.upsert_delete(query)


async def business_details_and_properties(tenant_id, by_tenant=False):
    business_query = f"""
        SELECT
            *
        FROM
            `businesses` b
        INNER JOIN
            `business_settings` bs
        ON
            b.id=bs.business_id
        WHERE
            `tenant_id` ='{tenant_id}'
    """
    business_res = await helperdao.fetchone_dict(business_query)
    business_id = business_res.get('business_id')
    business_res.pop("created_at")
    business_res.pop("updated_at")
    business_res.pop("bs.created_at")
    business_res.pop("bs.updated_at")
    if business_id:
        properties_query = f"""
            SELECT
                *
            FROM
                `business_properties` bp
            WHERE
                business_id='{business_id}'
        """
        properties_res = await helperdao.fetchall_dict(properties_query)
        properties = {}
        for property in properties_res:
            for key, value in property.items():
                properties[key] = value
        business_res.update(properties)
    return business_res if not by_tenant else {tenant_id: business_res}


async def enterprise_settings_and_properties():
    properties = {}
    settings = {}

    query = "SELECT * FROM `enterprise_properties`"
    res = await helperdao.fetchall_dict(query)

    for key, value in res:
        properties[key] = value

    query2 = "SELECT * FROM `enterprise_settings`"
    settings = await helperdao.fetchone_dict(query2)

    settings.update(properties)
    return settings


async def get_tenant_detail(tenant_id):
    query = f"""
        SELECT * FROM `businesses` WHERE `tenant_id`='{tenant_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return res.get("tenant_id") if res else None


async def get_favorite_charging_stations(tenant, user_id):
    query = f"""
        SELECT
            `location_id`
        FROM
            `tenant{tenant}`.`favorite_charging_stations`
        WHERE `user_id`='{user_id}';
    """
    location_ids = []
    res = await helperdao.fetchall_dict(query)
    for location in res:
        location_ids.append(location.get("location_id"))
    return {tenant: location_ids}


async def get_location_images_by_tenant(tenant_id):
    from server import MEDIA
    from urllib.parse import quote_plus

    locations = {}
    query = f"""
        SELECT
            *
        FROM `tenant{tenant_id}`.media
        WHERE
            model_type LIKE '%Location';
    """
    res = await helperdao.fetchall_dict(query)

    tenant = f"tenant_{tenant_id}"

    for location in res:
        url = f"""{MEDIA}/{tenant}/location/{location['id']}/{quote_plus(location["file_name"])}"""
        if location["model_id"] not in locations.keys():

            locations[location["model_id"]] = [url]
        else:
            locations[location["model_id"]].append(url)

    return {tenant_id: locations}


async def get_tenant_id_from_unique_code(unique_code):
    query = f"""
        SELECT tenant_id FROM charger_unique_codes
        WHERE unique_code='{unique_code}'
    """
    res = await helperdao.fetchone_dict(query)
    return res["tenant_id"] if res else ""
