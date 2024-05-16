# This file provides mysql connections from pool
from typing import Any
import aiomysql
from config import config


class MySqlDatabase:
    pool: Any = None

    async def init_pool():
        return await aiomysql.create_pool(
            host=config["MYSQL_HOST"],
            port=int(config["MYSQL_PORT"]),
            user=config["MYSQL_USER"],
            password=config["MYSQL_PASSWORD"],
            db=config["MYSQL_DB"],
            autocommit=True,
            echo=False,
        )

    @staticmethod
    async def get_pool():
        if MySqlDatabase.pool is None:
            MySqlDatabase.pool = await MySqlDatabase.init_pool()
        return MySqlDatabase.pool
