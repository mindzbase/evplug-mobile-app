import aiohttp


async def create_order(amount: float, currency: str, razorpay_keys: dict):
    url = "https://api.razorpay.com/v1/orders"
    async with aiohttp.ClientSession() as req:
        try:
            response = await req.post(
                auth=aiohttp.BasicAuth(razorpay_keys.get("API_KEY"),
                                       razorpay_keys.get("API_SECRET")),
                url=url,
                json={
                    "amount": amount,
                    "currency": currency,
                    "partial_payment": False
                },
                ssl=True,
            )
            data = await response.json()
            if response.status == 200:
                if data.get("error") is not None:
                    return None, data.get("description")
            return data.get("id"), data.get("status")
        except Exception as e:
            raise (e)