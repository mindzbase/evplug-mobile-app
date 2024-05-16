import logging
import random
import string
from errors.mysql_error import MySQLError
from dao import helperdao
import datetime

LOGGER = logging.getLogger("server")


async def create_new_user(
    name: str,
    email: str,
    os: str,
    token: str,
    phone: str,
    address: str,
    business_mobile_app: bool,
    tenant_id: str
):
    try:
        id_tag = "".join(random.choices(string.ascii_letters, k=7))
        user_table = (
            f"`tenant{tenant_id}`.`users`"
            if business_mobile_app
            else "`users`"
        )
        customer_table = (
            f"`tenant{tenant_id}`.`customer_invites`"
            if business_mobile_app
            else "`customer_invites`"
        )
        user_query = f"""
            INSERT INTO {user_table} (
                name,
                email,
                email_verified_at,
                password,
                phone_number,
                otp_required,
                is_customer,
                remember_token
            )
            VALUES (
                '{name}',
                '{email}',
                '{datetime.datetime.utcnow()}',
                'password',
                '{phone}',
                '{0}',
                '{1}',
                'abc'
                );
        """
        user_id = await helperdao.upsert_delete(user_query)

        customer_query = f"""
            INSERT INTO {customer_table}(email, user_id, name, wallet_balance,
            os, token, is_invited, phone, address) values ('{email}',
            '{user_id}', '{name}', {0}, '{os}', '{token}', {0},
            '{phone}', '{address}')
        """
        await helperdao.upsert_delete(customer_query)

        rfid_query = f"""
            INSERT into `tenant{tenant_id}`.`rfid_cards` (
                rfid_number,
                user_id,
                is_blocked,
                expiry_date
            ) VALUES ('{id_tag}', '{user_id}', 0, '2030-01-01');
        """
        await helperdao.upsert_delete(rfid_query)

        return user_id
    except Exception as e:
        raise MySQLError(str(e))


async def check_if_user_exists(email: str):
    try:
        query = f"""
            SELECT user_id, password from  WHERE email = '{email}'
        """
        res = await helperdao.fetchone(query)
        if res is not None:
            return (res[0], res[1])
        return None, None
    except Exception as e:
        raise MySQLError(str(e))


async def insert_otp_details(
    phone_number,
    otp,
    attempt,
    reference_id,
    aws_message_id,
    tenant_id,
    business_mobile_app
):
    try:
        table = (
            f"`tenant{tenant_id}`.`otp_details`"
            if business_mobile_app
            else '`otp_details`'
        )
        query = f"""INSERT into {table} (
            phone_number,
            otp,
            attempt,
            reference_id,
            aws_message_id
        ) VALUES (
            '{phone_number}',
            {otp},
            {attempt},
            '{reference_id}',
            '{aws_message_id}'
        )"""
        await helperdao.upsert_delete(query)
    except Exception as e:
        raise MySQLError(str(e))


async def get_user_details_by_phone(phone, tenant_id, business_mobile_app):
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
            phone='{phone}';
    """
    res = await helperdao.fetchone_dict(query)
    return res if res else {}


async def get_otp_with_reference_id(destination_number, reference_id, tenant_id, business_mobile_app):
    table = (
        f"`tenant{tenant_id}`.`otp_details`"
        if business_mobile_app
        else '`otp_details`'
    )
    query = f"""
        SELECT
            otp, created_at
        FROM
            {table}
        WHERE
            phone_number='{destination_number}'
        AND reference_id='{reference_id}'
    """
    res = await helperdao.fetchone_dict(query)
    return (res.get("otp"), res.get("created_at"))
