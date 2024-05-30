from constants import DefaultCaptureAmount, sort_order
from dao.app_dao import (
    get_all_charging_locations,
    get_all_charging_stations,
    get_all_child_businesses,
    get_all_third_party_charging_locations,
    get_group_plans,
    get_location_amenities,
    get_location_images,
    get_third_party_chargers,
    get_user_price_for_chargers,
)
from dao.user_dao import (
    check_and_get_if_user_authorize_on_charger,
    get_favorite_stations,
    get_holding_amount,
    get_recent_charging_stations,
)


async def get_children_of_enterprise():
    child_businesses = await get_all_child_businesses()
    return [x.get("tenant_id") for x in child_businesses]


async def get_tenant_ids_based_on_mobile_app(tenant_id, business_mobile_app):
    if not business_mobile_app:
        tenant_ids = await get_children_of_enterprise()
    elif business_mobile_app:
        tenant_ids = [tenant_id]
    return tenant_ids


async def get_charging_stations(
    org_ids,
    location_filter_ids,
    orgs_price_include_tax,
    orgs_currency,
    user_id,
):
    private_charger_list = await check_and_get_if_user_authorize_on_charger(
        user_id=user_id,
    )
    authorized_charger_list = [
        charger.get("charger_id") for charger in private_charger_list
    ]
    charging_stations = await get_all_charging_stations(
        org_ids,
        location_filter_ids,
        authorized_charger_list,
    )
    third_party_chargers = await get_third_party_chargers(org_ids)
    charging_stations.update(third_party_chargers)

    org_max_amounts = await get_holding_amount_of_organisation(org_ids=org_ids)
    for charging_station in charging_stations.values():
        charging_station["connectors"].sort(
            key=lambda x: sort_order.index(x["status"]))
        loc_org_id = charging_station.pop("org_id")
        price = charging_station.pop("price")
        bill_by = charging_station.pop("bill_by")
        for connector in charging_station["connectors"]:
            connector["price"] = price
            connector["bill_by"] = bill_by
            connector["plan_type"] = "public"
            connector["price_include_tax"] = bool(
                int(orgs_price_include_tax.get(loc_org_id, 0)),
            )
            connector["currency"] = orgs_currency.get(loc_org_id, "")
            connector["max_amount"] = org_max_amounts.get(loc_org_id).get(
                charging_station.get("type"),
            )
    return charging_stations


async def get_holding_amount_of_organisation(org_ids):
    org_ids_list = org_ids.split("', '")
    org_max_amounts = {}
    for org_id in org_ids_list:
        org_max_amounts[org_id] = {
            "AC": DefaultCaptureAmount.AC,
            "DC": DefaultCaptureAmount.DC,
        }
    holding_amount_details = await get_holding_amount(org_ids=org_ids)
    if holding_amount_details:
        temp = {
            detail.get("org_id"): {detail.get("charger_type"): detail.get("max_amount")}
            for detail in holding_amount_details
        }
        for key in org_max_amounts:
            if key in temp:
                org_max_amounts[key]["AC"] = (
                    temp[key]["AC"]
                    if temp[key].get("AC")
                    else org_max_amounts[key]["AC"]
                )
                org_max_amounts[key]["DC"] = (
                    temp[key]["DC"]
                    if temp[key].get("DC")
                    else org_max_amounts[key]["DC"]
                )
    return org_max_amounts


async def get_location_info(charging_stations, day, user_id):
    location_ids = [charger["location_id"]
                    for charger in charging_stations.values()]
    locations = await get_all_charging_locations(location_ids, day)
    third_party_location = await get_all_third_party_charging_locations(
        locations_ids=location_ids, day=day,
    )
    locations.update(third_party_location)
    amenities = await get_location_amenities(location_ids)
    images = await get_location_images(location_ids)
    group_plans = await get_group_plans(user_id)
    if group_plans:
        update_group_plans(charging_stations, group_plans)
    user_plans = await get_user_price_for_chargers(user_id)
    if user_plans:
        update_user_plans(charging_stations, user_plans)

    await update_favorite_station(locations, user_id, day)
    await update_recent_charging_station(locations, user_id, day)
    update_locations(locations, charging_stations,
                     amenities, images, sort_order)
    return locations


async def update_favorite_station(locations, user_id, day):
    fav_stations = await get_favorite_stations(user_id, day)
    favorites_list = []
    if fav_stations:
        favorites_list = list(fav_stations.keys())
    for location in locations.values():
        key = location.get("id")
        location["is_fav"] = key in favorites_list


async def update_recent_charging_station(locations, user_id, day):
    recent_location_ids = await get_recent_charging_stations(user_id=user_id, day=day)
    for location in locations.values():
        key = location.get("id")
        location["is_recent"] = key in recent_location_ids
        if location["is_recent"]:
            location["recent_order"] = recent_location_ids.index(key) + 1


def update_group_plans(charging_stations, group_plans):
    for plan in group_plans:
        charger_id = plan.get("charger_id")
        if charging_stations.get(charger_id):
            for connector in charging_stations[charger_id]["connectors"]:
                connector["price"] = plan.get("price", connector.get("price"))
                connector["bill_by"] = plan.get(
                    "billing_type", connector.get("bill_by"),
                )
                connector["plan_type"] = plan.get(
                    "plan_type", connector.get("plan_type"),
                )


def update_user_plans(charging_stations, user_plans):
    for plan in user_plans:
        charger_id = plan.get("charger_id")
        if charging_stations.get(charger_id):
            for connector in charging_stations[charger_id]["connectors"]:
                if connector.get("connector_id") == int(plan.get("connector_id")):
                    connector["price"] = plan.get(
                        "price", connector.get("price"))
                    connector["bill_by"] = plan.get(
                        "billing_type", connector.get("bill_by"),
                    )
                    connector["plan_type"] = plan.get(
                        "plan_type", connector.get("plan_type"),
                    )


def update_locations(locations, charging_stations, amenities, images, sort_order):
    for charging_station in charging_stations.values():
        location_id = charging_station["location_id"]
        if locations[location_id].get("chargers"):
            locations[location_id]["chargers"].append(charging_station)
        else:
            locations[location_id]["chargers"] = []
            locations[location_id]["chargers"].append(charging_station)

    for amenity in amenities:
        location_id = amenity
        locations[location_id]["amenities"] = amenities[amenity]

    for image in images:
        location_id = image
        locations[location_id]["images"] = images[image]

    for location in locations.values():
        location["chargers"] = sorted(
            location["chargers"],
            key=lambda x: sort_order.index(x["connectors"][0]["status"]),
        )


async def organise_recent_charging_station(recent_locations):
    results = []
    final_recent_stations = {}
    for recent_location in recent_locations:
        for tenant_id, locations in recent_location.items():
            sorted_locations = sorted(
                locations,
                key=lambda x: x['session_start_time'],
                reverse=True
            )
            top_3_locations = sorted_locations[:3]
            for i in top_3_locations:
                i['tenant_id'] = tenant_id
            results = [*results, *top_3_locations]
    sorted_all_locations = sorted(
        results,
        key=lambda x: x['session_start_time'],
        reverse=True
    )
    sorted_all_locations = sorted_all_locations[:3]
    for station in sorted_all_locations:
        tenant_id = station.pop('tenant_id')
        location_id = station.pop('location_id')
        if tenant_id in final_recent_stations.keys():
            final_recent_stations[tenant_id].append(location_id)
        else:
            final_recent_stations[tenant_id] = [location_id]
    return final_recent_stations
