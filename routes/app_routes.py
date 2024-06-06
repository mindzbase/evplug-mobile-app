import asyncio
import json
import logging

from aiohttp import web

from dao import app_dao
from errors.mysql_error import MissingObjectOnDB
from service_layers.app_layer import get_tenant_ids_based_on_mobile_app
from service_layers.app_layer import organise_recent_charging_station
import utils

LOGGER = logging.getLogger("server")
app_routes = web.RouteTableDef()


@app_routes.get("/app/charging_stations/")
async def get_all_charging_station_coordinates(request: web.Request) -> web.Response:
    try:
        user_id = request["user"]
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        day = request.query.get("day", "monday")
        location_filter_ids = [
            int(x) for x in request.query.get("location_ids", "").split(",") if x
        ]
        tenant_id_list = await get_tenant_ids_based_on_mobile_app(
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )

        if tenant_id_list:
            property_tasks = []
            location_tasks = []
            location_amenity_tasks = []
            location_review_tasks = []
            charger_tasks = []
            connector_tasks = []
            recent_location_tasks = []
            favorite_location_tasks = []
            images_tasks = []
            for tenant in tenant_id_list:
                property_tasks.append(
                    app_dao.business_details_and_properties(
                        tenant_id=tenant,
                        by_tenant=True
                    )
                )
                location_tasks.append(
                    app_dao.get_location_of_tenant(
                        tenant=tenant,
                        location_ids=location_filter_ids,
                        day=day,
                    ),
                )
                location_amenity_tasks.append(
                    app_dao.get_location_amenities_of_tenant(
                        tenant=tenant,
                        location_ids=location_filter_ids,
                    ),
                )
                location_review_tasks.append(
                    app_dao.get_location_review_of_tenant(
                        tenant=tenant,
                        location_ids=location_filter_ids,
                    ),
                )
                charger_tasks.append(
                    app_dao.get_location_chargers_of_tenant(
                        tenant=tenant,
                        location_ids=location_filter_ids,
                    ),
                )
                connector_tasks.append(
                    app_dao.charger_connector_of_tenant(
                        tenant=tenant, user_id=user_id),
                )
                recent_location_tasks.append(
                    app_dao.get_recent_charging_stations(
                        tenant=tenant,
                        user_id=user_id,
                    ),
                )
                favorite_location_tasks.append(
                    app_dao.get_favorite_charging_stations(
                        tenant=tenant,
                        user_id=user_id
                    )
                )
                images_tasks.append(
                    app_dao.get_location_images_by_tenant(tenant_id=tenant)
                )

            tenant_property = await asyncio.gather(*property_tasks)
            locations = await asyncio.gather(*location_tasks)
            location_amenities = await asyncio.gather(*location_amenity_tasks)
            location_reviews = await asyncio.gather(*location_review_tasks)
            chargers = await asyncio.gather(*charger_tasks)
            connectors = await asyncio.gather(*connector_tasks)
            recent_locations = await asyncio.gather(*recent_location_tasks)
            favorite_locations = await asyncio.gather(*favorite_location_tasks)
            images_locations = await asyncio.gather(*images_tasks)
            recent_locations_dict = await organise_recent_charging_station(
                recent_locations
            )
            tenant_properties = {}
            location_dict = {}
            connector_dict = {}
            charger_dict = {}
            amenities_dict = {}
            review_dict = {}
            fav_dict = {}
            images_dict = {}
            final_location_list = []
            for i in location_reviews:
                review_dict.update(i)
            for i in location_amenities:
                amenities_dict.update(i)
            for i in tenant_property:
                tenant_properties.update(i)
            for i in connectors:
                connector_dict.update(i)
            for i in chargers:
                charger_dict.update(i)
            for i in locations:
                location_dict.update(i)
            for i in favorite_locations:
                fav_dict.update(i)
            for i in images_locations:
                images_dict.update(i)

            for tenant, locations in location_dict.items():
                for location_id, location in locations.items():

                    if fav_dict.get(tenant):
                        location_list = fav_dict[tenant]
                        location["is_fav"] = (
                            True if location_id in location_list else False
                        )

                    if recent_locations_dict.get(tenant):
                        location_list = recent_locations_dict[tenant]
                        if location_id in location_list:
                            location["is_recent"] = True
                            location["recent_orders"] = (
                                location_list.index(location_id) + 1
                            )
                        else:
                            location["is_recent"] = False
                            location["recent_orders"] = 0

                    if tenant_properties.get(tenant):
                        location["currency"] = (
                            utils.get_currency_symbol(
                                tenant_properties[tenant].get("currency", "dollar"))
                        )
                        location["price_include_tax"] = (
                            tenant_properties[tenant].get(
                                "price_include_tax", False)
                        )
                    else:
                        location["price_include_tax"] = False

                    if amenities_dict.get(tenant):
                        location["amenities"] = (
                            amenities_dict[tenant].get(location_id, [])
                        )

                    if review_dict.get(tenant):
                        location["reviews"] = review_dict[tenant].get(
                            location_id, [])

                    if (
                        charger_dict.get(tenant)
                        and charger_dict[tenant].get(location_id)
                    ):
                        chargers = charger_dict[tenant][location_id]
                        temp_chargers = []
                        for charger in chargers:
                            charger_id = charger.get('charger_id')
                            charger["tenant_id"] = tenant
                            if (
                                connector_dict.get(tenant)
                                and connector_dict[tenant].get(location_id)
                            ):
                                if (
                                    connector_dict[tenant][location_id].get(
                                        charger_id)
                                ):
                                    charger['connectors'] = connector_dict[tenant][
                                        location_id][charger_id]
                                    temp_chargers.append(charger)
                        charger_dict[tenant][location_id] = temp_chargers

                    if charger_dict.get(tenant):
                        location["chargers"] = charger_dict[tenant].get(
                            location_id, [])

                    if images_dict.get(tenant):
                        location["images"] = images_dict[tenant].get(
                            location_id, [])

                    location.get(
                        'chargers') and final_location_list.append(location)

        return web.Response(
            status=200,
            body=json.dumps(final_location_list),
            content_type="application/json",
        )

    except MissingObjectOnDB as e:
        LOGGER.error(e)
        return e.jsonResponse

    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@app_routes.get("/app/get_connector_types/")
async def get_connector_type(request: web.Request) -> web.Response:
    try:
        request["user"]
        tenant_id = request["tenant_id"]
        business_mobile_app = request["business_mobile_app"]
        tenant_ids = await get_tenant_ids_based_on_mobile_app(
            tenant_id=tenant_id,
            business_mobile_app=business_mobile_app,
        )
        res = await app_dao.get_connector_list(tenant_id)
        return web.Response(
            status=200,
            body=json.dumps(res),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@app_routes.get("/app/get_faq/")
async def get_organisation_faq(request: web.Request) -> web.Response:
    try:
        request["user"]
        tenant_id = request["tenant_id"]
        res = await app_dao.get_organisation_faq(tenant_id)
        return web.Response(
            status=200,
            body=json.dumps(res),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )


@app_routes.get("/app/header_signin/")
async def header_signin(request: web.Request) -> web.Response:
    try:
        request["user"]
        return web.Response(
            status=200,
            body=json.dumps({"login": True}),
            content_type="application/json",
        )
    except Exception as e:
        LOGGER.error(e)
        return web.Response(
            status=500,
            body=json.dumps(
                {"msg": f"Internal Server error occured with error {e}"}),
            content_type="application/json",
        )
