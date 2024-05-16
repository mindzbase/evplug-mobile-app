from typing import Any
import aiohttp
from config import config


async def call_lambda_function(body: Any) -> int:
    headers = {"Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            config["LAMBDA_URL"], json=body, headers=headers
        ) as resp:
            res = await resp.json()
            return resp.status, res
