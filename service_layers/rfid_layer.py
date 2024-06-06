import asyncio
from dao.user_dao import enterprise_id_tags, get_id_tags_by_user_id


async def get_enterprise_cards(user_id, business_mobile_app):
    if not business_mobile_app:
        enterprise_cards = await enterprise_id_tags(user_id=user_id)
        return enterprise_cards
    return []


async def get_tenant_cards(user_id, tenant_id_list):
    tasks = [
        get_id_tags_by_user_id(user_id=user_id, tenant_id=tenant_id)
        for tenant_id in tenant_id_list
    ]
    return await asyncio.gather(*tasks)


def combine_all_cards(enterprise_cards, tenant_cards_results):
    combined_cards = {}
    for tenant_card in tenant_cards_results:
        for tenant, cards in tenant_card.items():
            combined_cards.setdefault(tenant, []).extend(cards)
    for tenant, cards in combined_cards.items():
        cards.extend(enterprise_cards)
    return combined_cards


async def get_rfid_of_user(
    business_mobile_app,
    user_id,
    tenant_id_list
):
    try:
        enterprise_cards = await get_enterprise_cards(user_id, business_mobile_app)
        tenant_cards = await get_tenant_cards(user_id, tenant_id_list)
        combined_cards = combine_all_cards(enterprise_cards, tenant_cards)
        return combined_cards

    except Exception as e:
        raise e("Fetching User RFID Card with")
