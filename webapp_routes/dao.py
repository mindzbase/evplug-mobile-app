from dao import helperdao


async def get_connector_details(charger_id, connector_id):
    query = f"""
        SELECT
            c.id,
            c.charger_name as charger_name,
            cc.connector_id,
            cc.type,
            cc.status,
            cc.max_output,
            pp.billing_type,
            pp.price,
            pp.idle_charging_fee,
            pp.apply_after,
            l.org_id
        FROM
            `charger_details` c
        INNER JOIN `charger_connector_details` cc ON
            c.id = cc.charger_id
        INNER JOIN `price_plans` pp ON
            c.price_id = pp.price_id
        INNER JOIN `locations` l ON
            c.location_id=l.id
        WHERE
        c.id='{charger_id}' AND cc.connector_id='{connector_id}';
    """
    res = await helperdao.fetchone_dict(query)
    return {} if not res else res


async def get_generic_vehicle():
    query = """
        SELECT id FROM `vehicles` WHERE manufacturer='generic' AND model='car'
    """
    res = await helperdao.fetchone_dict(query)
    return res.get("id") if res else None


async def add_generic_vehicle():
    query = """
        INSERT INTO `vehicles` VALUES (
            NULL, 'generic', 'car', '0',
            '0', 'a', NULL, current_timestamp()
        );
    """
    vehicle_id = await helperdao.upsert_delete(query)
    return vehicle_id


async def link_generic_vehicle_with_user(vehicle_id, user_id):
    query = f"""
        INSERT INTO `users_vehicle`(`user_id`, `vehicle_id`, `is_default`)
        VALUES ('{user_id}','{vehicle_id}','1')
    """
    await helperdao.upsert_delete(query)
    return


async def get_session_id(charger_id, connector_id, id_tag):
    query = f"""
        SELECT id FROM sessions WHERE charger_id='{charger_id}'
        AND connector_id='{connector_id}' AND start_id_tag='{id_tag}'
        AND is_running='1'
    """
    res = await helperdao.fetchone_dict(query)
    return res.get("id") if res else None


async def create_webapp_user(user_id, email, org_id):
    query = f"""
        INSERT INTO `users`(`user_id`, `email`, `is_mobile_app_user`, `org_id`)
        VALUES('{user_id}','{email}','{0}','{org_id}')
    """
    await helperdao.upsert_delete(query)
    return


async def get_web_app_user(email):
    query = f"""
        SELECT user_id FROM `users` WHERE `email`='{email}'
        AND `is_mobile_app_user`="{0}"
    """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def add_rfid_user(id_tag, user_id, org_id):
    rfid_query = f"""
            INSERT into rfid_cards (id_tag, user_id, is_blocked, expiry_date,
            is_parent, parent_id_tag, org_id) VALUES ('{id_tag}', '{user_id}', 0,
            '2030-01-01', 1, NULL, '{org_id}')
        """
    await helperdao.upsert_delete(rfid_query)
    return


async def verify_webapp_user(user_id):
    query = f"""
        SELECT * FROM users WHERE user_id='{user_id}' AND is_mobile_app_user="{0}"
    """
    res = await helperdao.fetchone_dict(query)
    return res.get("user_id") if res else None
