import asyncio
import logging
import aiohttp_cors
import websockets
from aiohttp import web
# from dao.helperdao import check_and_create_table
from websocket import server_func
from middleware import tenant_and_user_middleware
from routes import auth_routes, user_routes, session_routes
from routes import app_routes, vehicle_routes, ocpp_routes
from webapp_routes import webapp_routes

# WORKING_DIR = Path(__file__).resolve().parent
# LOGFILE_LOCATION = os.path.join(WORKING_DIR, 'logs/server.log')

# server_file_handler = logging.FileHandler(LOGFILE_LOCATION)
logging.basicConfig(
    format="""
        %(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s
    """,
    datefmt="%Y-%m-%d:%H:%M:%S",
    level=logging.DEBUG,
    force=True,
)


async def main():
    app = web.Application(
        middlewares=[
            tenant_and_user_middleware,
        ]
    )
    app.add_routes(auth_routes.auth_routes)
    app.add_routes(user_routes.user_routes)
    app.add_routes(session_routes.session_routes)
    app.add_routes(app_routes.app_routes)
    app.add_routes(vehicle_routes.vehicle_routes)
    app.add_routes(ocpp_routes.ocpp_routes)
    app.add_routes(webapp_routes.webapp_routes)
    cors = aiohttp_cors.setup(
        app,
        defaults={
            "*": aiohttp_cors.ResourceOptions(
                allow_credentials=True,
                expose_headers="*",
                allow_headers="*",
                allow_methods=["GET", "POST", "OPTION"],
            )
        },
    )
    for route in list(app.router.routes()):
        cors.add(route)
    from config import config

    server = await websockets.serve(server_func, "0.0.0.0", config["WEBSOCKET_PORT"])
    runner = web.AppRunner(app)
    await runner.setup()
    # await check_and_create_table()
    site = web.TCPSite(runner, "0.0.0.0", config["WEBSERVER_PORT"])
    # await asyncio.wait([server.wait_closed(), site.start(), init_consumer()])
    # await asyncio.wait([server.wait_closed(), site.start()])
    logging.info('reaching to server.py in info file')
    await asyncio.wait([asyncio.create_task(server.wait_closed()), asyncio.create_task(site.start())])

try:
    asyncio.run(main())
except KeyboardInterrupt:
    print("""
        ================================================
        ----------- Program existed by user ------------
        ================================================
    """)
except Exception as e:
    print(e)
