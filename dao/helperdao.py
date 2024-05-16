import logging
from typing import Any
import aiomysql
from database import MySqlDatabase
from errors.mysql_error import MySQLError

LOGGER = logging.getLogger("server")


async def fetchall(query) -> Any:
    try:
        pool = await MySqlDatabase.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query)
                res = await cur.fetchall()
                if res is not None:
                    return res
                return None
    except Exception as e:
        raise MySQLError(str(e))


async def fetchone(query) -> Any:
    try:
        pool = await MySqlDatabase.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query)
                res = await cur.fetchone()
                if res is not None:
                    return res
                return None
    except Exception as e:
        raise MySQLError(str(e))


async def fetchall_dict(query) -> Any:
    try:
        pool = await MySqlDatabase.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query)
                res = await cur.fetchall()
                if res:
                    return res
                return []
    except Exception as e:
        raise MySQLError(str(e))


async def fetchone_dict(query) -> Any:
    try:
        pool = await MySqlDatabase.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(query)
                res = await cur.fetchone()
                if res:
                    return res
                return {}
    except Exception as e:
        raise MySQLError(str(e))


async def upsert_delete(query):
    try:
        pool = await MySqlDatabase.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                try:
                    await cur.execute(query)
                    res = cur.lastrowid
                    if res is not None:
                        return res
                    return None
                except Exception as e:
                    await conn.rollback()
                    raise (e)
    except Exception as e:
        raise MySQLError(str(e))


async def table_exists(table_name):
    try:
        pool = await MySqlDatabase.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    query = f"SHOW TABLES LIKE '{table_name}'"
                    await cursor.execute(query)
                    result = await cursor.fetchall()
                    return len(result) > 0
                except Exception as e:
                    await conn.rollback()
                    raise (e)
    except Exception as e:
        raise MySQLError(str(e))


async def column_exists(table_name, column_name):
    try:
        pool = await MySqlDatabase.get_pool()
        async with pool.acquire() as conn:
            async with conn.cursor() as cursor:
                try:
                    query = f"""
                        SELECT column_name FROM information_schema.columns
                        WHERE table_name = '{table_name}'
                        AND column_name = '{column_name}'
                    """
                    await cursor.execute(query)
                    result = await cursor.fetchall()
                    return len(result) > 0
                except Exception as e:
                    await conn.rollback()
                    raise (e)
    except Exception as e:
        raise MySQLError(str(e))


async def check_and_create_table():
    tables = [
        "invoice",
        "stripe_customers",
        "sent_firebase_notifications",
        "holding_cards_payment_intents",
        "holding_cards_payment_status",
        "organisation_holding_charges",
        "session_payment_method",
        "card_logos",
        "faq_organisations",
        "charger_details",
        "user_details",
        "session_firebase_notificaions",
        "charger_networks",
        "user_sessions"
    ]
    create_table = {
        "faq_organisations": """
            CREATE TABLE `faq_organisations` (`id` INT NOT NULL AUTO_INCREMENT,
            `org_id` VARCHAR(255) NOT NULL, `question` VARCHAR(1000) NOT NULL,
            `answer` VARCHAR(1000) NOT NULL, `created_at` timestamp NOT NULL
            DEFAULT current_timestamp(), PRIMARY KEY (`id`));""",
        "sent_firebase_notifications": """
            CREATE TABLE `sent_firebase_notifications` (
            `id` int(11) auto_increment NOT NULL primary key,
            `user_id` varchar(255) DEFAULT NULL,
            `session_id` int(11) DEFAULT NULL,
            `event_name` varchar(255) DEFAULT NULL,
            `json` varchar(1000) DEFAULT NULL,
            `created_at` datetime NOT NULL DEFAULT current_timestamp()
            );""",
        "stripe_customers": """
            CREATE TABLE `stripe_customers` (
            `id` INT NOT NULL AUTO_INCREMENT ,
            `user_id` VARCHAR(255) NOT NULL ,
            `cust_id` VARCHAR(255) NOT NULL ,
            `created_at` TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ,
            PRIMARY KEY (`id`)
            );
        """,
        "holding_cards_payment_intents": """
            CREATE TABLE `holding_cards_payment_intents` (
                `id` int(11) NOT NULL,
                `payment_intent_id` varchar(255) NOT NULL,
                `payment_method_id` varchar(255) NOT NULL,
                `charger_id` varchar(255) NOT NULL,
                `connector_id` int(11) NOT NULL,
                `user_id` varchar(255) NOT NULL,
                `cust_id` varchar(255) NOT NULL,
                `amount` float NOT NULL,
                `currency` varchar(255) NOT NULL,
                `created_at` timestamp NOT NULL DEFAULT current_timestamp()
            );
            ALTER TABLE `holding_cards_payment_intents`
            ADD PRIMARY KEY (`id`);
            ALTER TABLE `holding_cards_payment_intents`
            MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;
        """,
        "holding_cards_payment_status": """
            CREATE TABLE `holding_cards_payment_status` (
            `id` int(11) NOT NULL,
            `payment_intent_id` varchar(255) NOT NULL,
            `max_amount` float NOT NULL,
            `amount_captured` int(11) NOT NULL,
            `amount_refunded` float NOT NULL,
            `txn_charge_id` varchar(255) NOT NULL,
            `currency` varchar(10) NOT NULL,
            `cust_id` varchar(255) NOT NULL,
            `receipt_url` varchar(255) NOT NULL,
            `status` varchar(255) NOT NULL,
            `created_at` timestamp NOT NULL DEFAULT current_timestamp()
            );
            ALTER TABLE `holding_cards_payment_status`
            ADD PRIMARY KEY (`id`);
            ALTER TABLE `holding_cards_payment_status`
            MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;
        """,
        "organisation_holding_charges": """
            CREATE TABLE `organisation_holding_charges` (
                `id` int(11) NOT NULL,
                `org_id` varchar(255) NOT NULL,
                `max_amount` int(11) NOT NULL,
                `charger_type` varchar(255) NOT NULL,
                `created_at` timestamp NOT NULL DEFAULT current_timestamp()
            );
            ALTER TABLE `organisation_holding_charges`
            ADD PRIMARY KEY (`id`);
            ALTER TABLE `organisation_holding_charges`
            MODIFY `id` int(11) NOT NULL AUTO_INCREMENT;
        """,
        "session_payment_method": """
            CREATE TABLE `session_payment_method` (`id` INT NOT NULL
            AUTO_INCREMENT , `session_id` INT NOT NULL , `payment_intent_id`
            VARCHAR(255) NOT NULL , `created_at` timestamp NOT NULL
            DEFAULT current_timestamp(), PRIMARY KEY (`id`));
        """,
        "card_logos": """
            CREATE TABLE `card_logos` (`id` INT NOT NULL
            AUTO_INCREMENT , `name` VARCHAR(255) NOT NULL , `logo_url`
            VARCHAR(255) NOT NULL , `created_at` timestamp NOT NULL
            DEFAULT current_timestamp(), PRIMARY KEY (`id`));
            INSERT INTO `card_logos` (`id`, `name`, `logo_url`, `created_at`) VALUES
            (1, 'visa', 'https://najhumimages.s3.me-central-1.amazonaws.com/card_logos/visa.png', '2023-11-09 08:07:33'),
            (2, 'discover', 'https://najhumimages.s3.me-central-1.amazonaws.com/card_logos/discover.png', '2023-11-09 08:07:33'),
            (3, 'mastercard', 'https://najhumimages.s3.me-central-1.amazonaws.com/card_logos/mastercard.png', '2023-11-09 08:08:42'),
            (4, 'generic', 'https://najhumimages.s3.me-central-1.amazonaws.com/card_logos/generic.png', '2023-11-09 08:09:42'),
            (5, 'rupay', 'https://najhumimages.s3.me-central-1.amazonaws.com/card_logos/rupay.png', '2023-11-09 08:10:38'),
            (6, 'amex', 'https://najhumimages.s3.me-central-1.amazonaws.com/card_logos/amex.png', '2023-11-09 08:10:38');
        """,  # noqa
        "user_details": """
            CREATE TABLE `user_details` (`id` INT NOT NULL AUTO_INCREMENT ,
            `user_id` VARCHAR(255) NOT NULL ,
            `firebase_uid` VARCHAR(255) NULL ,
            `name` VARCHAR(100) NOT NULL ,
            `phone` VARCHAR(100) NOT NULL ,
            `address` VARCHAR(255) NULL ,
            `pincode` VARCHAR(255) NULL ,
            `wallet_balance` FLOAT NOT NULL DEFAULT '0' ,
            `is_email_verified` BOOLEAN NOT NULL DEFAULT FALSE ,
            `token` VARCHAR(1000) NULL ,
            `os` ENUM('android','ios') NOT NULL,
            `org_id` VARCHAR(255) NOT NULL,
            `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
            `updated_at` TIMESTAMP on update current_timestamp() NOT NULL DEFAULT
            current_timestamp(), PRIMARY KEY (`id`),
            KEY `phone_org1` (`phone`,`org_id`));

            INSERT INTO user_details (user_id, firebase_uid, name, phone, address,
            pincode, wallet_balance, is_email_verified, token, os, org_id, created_at,
            updated_at) SELECT user_id, firebase_uid, name, phone, address, pincode,
            wallet_balance, is_email_verified, token, os, org_id, created_at, updated_at
            FROM users;

            ALTER TABLE `users` ADD `is_mobile_app_user`
            BOOLEAN NOT NULL DEFAULT TRUE AFTER `email`;

            ALTER TABLE users ADD KEY `email_app` (`email`,`is_mobile_app_user`);
            ALTER TABLE `users` CHANGE `name` `name` VARCHAR(1000) NULL;
            ALTER TABLE `users` CHANGE `firebase_uid` `firebase_uid` VARCHAR(255) NULL;
            ALTER TABLE `users` CHANGE `phone` `phone` VARCHAR(100) NULL;
            ALTER TABLE `users` CHANGE `pincode` `pincode` VARCHAR(255) NULL;
            ALTER TABLE `users` CHANGE `address` `address` VARCHAR(255) NULL;
            ALTER TABLE `users` CHANGE `os` `os` ENUM('android','ios') NOT NULL DEFAULT 'android';
            """,
        "session_firebase_notificaions": """
            CREATE TABLE `session_firebase_notificaions` (`id` INT NOT NULL
            AUTO_INCREMENT , `session_id` INT NOT NULL , `notification_type`
            VARCHAR(255) NOT NULL , `notification_value` VARCHAR(255) NOT NULL,
            `created_at` TIMESTAMP NOT NULL DEFAULT current_timestamp(),
            `updated_at` TIMESTAMP on update current_timestamp() NOT NULL DEFAULT
            current_timestamp() , PRIMARY KEY (`id`));
        """,
        "user_sessions": """
            CREATE TABLE `user_sessions` (
            `id` int(11) NOT NULL AUTO_INCREMENT,
            `user_id` varchar(255) NOT NULL,
            `expiry_date` datetime NOT NULL,
            `created_at` timestamp NOT NULL DEFAULT current_timestamp(),
            `updated_at` timestamp NOT NULL DEFAULT current_timestamp()
                ON UPDATE current_timestamp(),
            PRIMARY KEY (`id`));
        """,
        "charger_networks": """
            CREATE TABLE `charger_networks` (`id` INT NOT NULL AUTO_INCREMENT ,
            `name` VARCHAR(255) NOT NULL , `logo_url` VARCHAR(255) NOT NULL ,
            `created_at` TIMESTAMP NOT NULL DEFAULT current_timestamp(),
            PRIMARY KEY (`id`));


            INSERT INTO `charger_networks` (`id`, `name`, `logo_url`, `created_at`)
            VALUES (
                1,
                'Ather',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/Ather.png',
                '2024-01-03 09:12:33'
            ),
            (
                2,
                'BPCL',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/BPCL.png',
                '2024-01-03 09:12:33'
            ),
            (
                3,
                'Chargegrid',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/Chargegrid.png',
                '2024-01-03 09:12:33'
            ),
            (
                4,
                'Chargezone',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/Chargezone.png',
                '2024-01-03 09:12:33'
            ),
            (
                5,
                'Glida',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/Glida.png',
                '2024-01-03 09:12:33'
            ),
            (
                6,
                'HPCL',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/HPCL.png',
                '2024-01-03 09:12:33'
            ),
            (
                7,
                'IOCL',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/IOCL.png',
                '2024-01-03 09:12:33'
            ),
            (
                8,
                'OLA',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/OLA.png',
                '2024-01-03 09:12:33'
            ),
            (
                9,
                'Statiq',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/Statiq.png',
                '2024-01-03 09:12:33'
            ),
            (
                10,
                'Tata',
                'https://sock8-sg.s3.ap-southeast-1.amazonaws.com/sock8/media/network-brands-logo/Tata.png',
                '2024-01-03 09:12:33'
            ),
            (
                11,
                'Allego',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Allego.png',
                '2024-01-03 09:12:33'
            ),
            (
                12,
                'Be.EV',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Be.EV.png',
                '2024-01-03 09:12:33'
            ),
            (
                13,
                'Believ',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Believ.png',
                '2024-01-03 09:12:33'
            ),
            (
                14,
                'Blink Charging',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Blink+Charging.png',
                '2024-01-03 09:12:33'
            ),
            (
                15,
                'BP-Pulse (POLAR)',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/BP-Pulse+(POLAR).png',
                '2024-01-03 09:12:33'
            ),
            (
                16,
                'Char.gy',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Char.gy.png',
                '2024-01-03 09:12:33'
            ),
            (
                17,
                'Charge Your Car',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Charge+Your+Car.png',
                '2024-01-03 09:12:33'
            ),
            (
                18,
                'ChargePlace Scotland',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/ChargePlace+Scotland.png',
                '2024-01-03 09:12:33'
            ),
            (
                19,
                'Clenergy EV',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Clenergy+EV.png',
                '2024-01-03 09:12:33'
            ),
            (
                20,
                'Connected Kerb',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Connected+Kerb.png',
                '2024-01-03 09:12:33'
            ),
            (
                21,
                'Dragon Charging Network',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Dragon+Charging+Network.png',
                '2024-01-03 09:12:33'
            ),
            (
                22,
                'E.ON Drive',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/E.ON+Drive.png',
                '2024-01-03 09:12:33'
            ),
            (
                23,
                'ecars ESB',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/ecars+ESB.png',
                '2024-01-03 09:12:33'
            ),
            (
                24,
                'ENGIE Charge Network',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/ENGIE+Charge+Network.png',
                '2024-01-03 09:12:33'
            ),
            (
                25,
                'eo Charging',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/eo+Charging.png',
                '2024-01-03 09:12:33'
            ),
            (
                26,
                'EV-Dot',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/EV-Dot.png',
                '2024-01-03 09:12:33'
            ),
            (
                27,
                'Fastned',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Fastned.png',
                '2024-01-03 09:12:33'
            ),
            (
                28,
                'GRIDSERVE Sustainable Energy',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/GRIDSERVE+Sustainable+Energy.png',
                '2024-01-03 09:12:33'
            ),
            (
                29,
                'Hubsta',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Hubsta.png',
                '2024-01-03 09:12:33'
            ),
            (
                30,
                'InstaVolt LTD',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/InstaVolt+LTD.png',
                '2024-01-03 09:12:33'
            ),
            (
                31,
                'IONITY GmbH',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/IONITY+GmbH.png',
                '2024-01-03 09:12:33'
            ),
            (
                32,
                'JOLT Charge Limited',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/JOLT+Charge+Limited.png',
                '2024-01-03 09:12:33'
            ),
            (
                33,
                'mer',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/mer.png',
                '2024-01-03 09:12:33'
            ),
            (
                34,
                'Merseytravel',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Merseytravel.png',
                '2024-01-03 09:12:33'
            ),
            (
                35,
                'OpCharge UK',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/OpCharge+UK.png',
                '2024-01-03 09:12:33'
            ),
            (
                36,
                'Osprey',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Osprey.png',
                '2024-01-03 09:12:33'
            ),
            (
                37,
                'Plug N Go Ltd',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Plug+N+Go+Ltd.png',
                '2024-01-03 09:12:33'
            ),
            (
                38,
                'Plugged-in Midlands',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Plugged-in+Midlands.png',
                '2024-01-03 09:12:33'
            ),
            (
                39,
                'POD Point',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/POD+Point.png',
                '2024-01-03 09:12:33'
            ),
            (
                40,
                'Scottish Power',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Scottish+Power.png',
                '2024-01-03 09:12:33'
            ),
            (
                41,
                'Shell Recharge Solutions',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Shell+Recharge+Solutions.png',
                '2024-01-03 09:12:33'
            ),
            (
                42,
                'Source London',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Source+London.png',
                '2024-01-03 09:12:33'
            ),
            (
                43,
                'SureCharge',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/SureCharge.png',
                '2024-01-03 09:12:33'
            ),
            (
                44,
                'Swarco E.Connect',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Swarco+E.Connect.png',
                '2024-01-03 09:12:33'
            ),
            (
                45,
                'The GeniePoint Network',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/The+GeniePoint+Network.png',
                '2024-01-03 09:12:33'
            ),
            (
                46,
                'Trojan Energy Limited',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Trojan+Energy+Limited.png',
                '2024-01-03 09:12:33'
            ),
            (
                47,
                'ubitricity',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/ubitricity.png',
                '2024-01-03 09:12:33'
            ),
            (
                48,
                'Zest',
                'https://sock8-eng.s3.eu-west-1.amazonaws.com/sock8/media/network-brands-logo/Zest.png',
                '2024-01-03 09:12:33'
            );
        """,
    }

    for table in tables:
        exist = await table_exists(table)
        if not exist:
            try:
                await upsert_delete(create_table.get(table))
            except Exception as e:
                LOGGER.error(e)

        else:
            await check_and_create_column(table)


async def check_and_create_column(table):
    check_columns = {
        "invoice": [
            "idle_minutes",
            "idle_price",
            "idle_charging_cost",
            "gateway_fee",
        ],
        "charger_details": ["is_third_party_charger"],
    }
    create_column_list = {
        "invoice": {
            "idle_minutes": "ALTER TABLE `invoice` ADD `idle_minutes` INT NULL;",
            "idle_price": "ALTER TABLE `invoice` ADD `idle_price` FLOAT NULL;",
            "idle_charging_cost": """
                ALTER TABLE `invoice` ADD `idle_charging_cost` FLOAT NULL;
            """,
            "gateway_fee": """
                ALTER TABLE `invoice` ADD `gateway_fee` FLOAT
                NOT NULL DEFAULT '0' AFTER `charging_cost_with_tax`;
            """,
        },
        "charger_details": {
            "is_third_party_charger": """
                ALTER TABLE `charger_details` ADD `is_third_party_charger` BOOLEAN
                NOT NULL DEFAULT FALSE AFTER `hide_on_map`, ADD
                `third_party_brand_name` VARCHAR(255) NOT NULL DEFAULT 'sock8'
                AFTER `is_third_party_charger`;"""
        },
    }
    if check_columns.get(table):
        for column in check_columns.get(table):
            exist = await column_exists(table, column)
            if not exist:
                await upsert_delete(create_column_list.get(table).get(column))
