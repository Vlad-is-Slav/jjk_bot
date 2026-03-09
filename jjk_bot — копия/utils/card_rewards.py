import random

from sqlalchemy import select

from models import Card, UserCard
from utils.card_data import ALL_CARDS, CHARACTER_CARDS, RARITY_CHANCES
from utils.daily_quest_progress import add_daily_quest_progress
from utils.quote_rewards import grant_quote_for_card


def _normalize_name(value: str) -> str:
    return "".join(ch.lower() for ch in (value or "") if ch.isalnum())


CHARACTER_CARD_NAMES = {card["name"] for card in CHARACTER_CARDS}
CHARACTER_CARD_NORMALIZED = {_normalize_name(card["name"]) for card in CHARACTER_CARDS}


def get_card_data_by_name(name: str):
    normalized = _normalize_name(name)
    for card in ALL_CARDS:
        if _normalize_name(card["name"]) == normalized:
            return card
    return None


def get_card_type_by_name(card_name: str) -> str:
    return "character" if _normalize_name(card_name) in CHARACTER_CARD_NORMALIZED else "support"


def is_character_template(card_template) -> bool:
    if not card_template:
        return False
    if _normalize_name(card_template.name) in CHARACTER_CARD_NORMALIZED:
        return True
    return card_template.card_type == "character"


def is_support_template(card_template) -> bool:
    if not card_template:
        return False
    if _normalize_name(card_template.name) in CHARACTER_CARD_NORMALIZED:
        return False
    if card_template.card_type == "character":
        return False
    return True


def roll_random_card_data(only_characters: bool = False):
    pool = CHARACTER_CARDS if only_characters else ALL_CARDS
    rand = random.uniform(0, 100)
    cumulative = 0.0
    selected_rarity = "common"

    for rarity, chance in RARITY_CHANCES.items():
        cumulative += float(chance)
        if rand <= cumulative:
            selected_rarity = rarity
            break

    cards_of_rarity = [card for card in pool if card["rarity"] == selected_rarity]
    if not cards_of_rarity:
        cards_of_rarity = [card for card in pool if card["rarity"] == "common"] or pool
    return random.choice(cards_of_rarity)


async def get_or_create_card_template(session, card_data: dict):
    result = await session.execute(
        select(Card).where(Card.name == card_data["name"])
    )
    card_template = result.scalar_one_or_none()

    expected_type = get_card_type_by_name(card_data["name"])
    if card_template:
        # Исправляем старые шаблоны, где тип мог быть определен неверно.
        if card_template.card_type != expected_type:
            card_template.card_type = expected_type
        return card_template

    card_template = Card(
        name=card_data["name"],
        description=card_data.get("description"),
        card_type=expected_type,
        rarity=card_data["rarity"],
        base_attack=card_data["base_attack"],
        base_defense=card_data["base_defense"],
        base_speed=card_data["base_speed"],
        base_hp=card_data["base_hp"],
        growth_multiplier=card_data["growth_multiplier"],
    )
    session.add(card_template)
    await session.flush()
    return card_template


async def grant_card_to_user(session, user_id: int, card_data: dict, level: int = 1):
    card_template = await get_or_create_card_template(session, card_data)

    user_card = UserCard(
        user_id=user_id,
        card_id=card_template.id,
        level=max(1, int(level)),
    )
    user_card.card_template = card_template
    user_card.recalculate_stats()
    session.add(user_card)

    await grant_quote_for_card(session, user_id, card_template.name)
    await add_daily_quest_progress(session, user_id, "obtain_cards", amount=1)
    return user_card


async def grant_random_card(session, user_id: int, only_characters: bool = False, level: int = 1):
    card_data = roll_random_card_data(only_characters=only_characters)
    user_card = await grant_card_to_user(session, user_id, card_data, level=level)
    return user_card
