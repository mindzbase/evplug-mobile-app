import datetime
import re
from dao import user_dao
from dao import app_dao
from aiohttp import web


# async def validate_token(user_id: str, tenant_id: str, business_mobile_app: bool):
#     try:
#         is_valid_token = await user_dao.validate_token(
#             user_id=user_id,
#             business_mobile_app=business_mobile_app,
#             tenant_id=tenant_id
#         )
#         if is_valid_token:
#             return user_id
#         raise web.HTTPNetworkAuthenticationRequired(reason="Login Expired")
#     except Exception as e:
#         raise (e)


async def validate_token(user_id: str, tenant_id: str, business_mobile_app: bool):
    try:
        is_valid_token = await user_dao.validate_token(
            user_id=user_id,
            business_mobile_app=business_mobile_app,
            tenant_id=tenant_id
        )
        if is_valid_token:
            res = await app_dao.get_user_login_session(
                user_id=user_id,
                business_mobile_app=business_mobile_app,
                tenant_id=tenant_id,
            )
            login = False
            current_datetime = datetime.datetime.utcnow()
            if res:
                expiry_date = res.get('expiry_date')
                login = True if expiry_date > current_datetime else False
            if login:
                difference_time = expiry_date - current_datetime
                if (difference_time.days < 7):
                    new_expiry_date = current_datetime + \
                        datetime.timedelta(days=7)
                    await app_dao.update_session_expiry_time(
                        user_id=user_id,
                        new_expiry_date=new_expiry_date,
                        business_mobile_app=business_mobile_app,
                        tenant_id=tenant_id,
                    )
                return user_id
        raise web.HTTPNetworkAuthenticationRequired(reason="Login Expired")
    except Exception as e:
        raise (e)


async def validate_tenant(tenant_id):
    try:
        res = await app_dao.get_tenant_detail(tenant_id=tenant_id)
        if res:
            return res
        raise web.HTTPUnauthorized(reason="Unautorized Business/Organisation")
    except Exception as e:
        raise e


@web.middleware
async def tenant_and_user_middleware(request, handler):
    try:
        exclude_paths = [
            r"/auth/\w+",
            r"/vehicles/\w+",
            r"/auth/\w+/",
            r"/server/\w+/",
            r"/server/\w+/\w+/",
            r"\/webapp\/\w+\/[\w-]+\/\w+\/\w+\/",
            r"\/webapp\/user\/[0-9a-fA-F-]+\/save_captured_card\/"
            r"\/webapp\/\w+\/\w+/",
            r"\/webapp\/\w+\/\w+\/",
            r"\/webapp\/\w+\/",
        ]
        tenant_id = request.headers.get("tenant_id")
        await validate_tenant(tenant_id=tenant_id)
        request['tenant_id'] = tenant_id
        business_mobile_app = await app_dao.does_business_have_mobile_app(tenant_id)
        request['business_mobile_app'] = business_mobile_app
        compiled_exclude_paths = [re.compile(pattern) for pattern in exclude_paths]
        if any(pattern.match(request.path) for pattern in compiled_exclude_paths):
            return await handler(request)
        else:
            authorization = request.headers.get('Authorization')
            user_id = authorization.replace('token ', '')
            await validate_token(
                user_id=user_id,
                tenant_id=tenant_id,
                business_mobile_app=business_mobile_app
            )
            request['user'] = user_id
            response = await handler(request)
            return response
    except web.HTTPUnauthorized as e:
        raise e
    except web.HTTPNetworkAuthenticationRequired as e:
        raise e
    except Exception as e:
        raise e
