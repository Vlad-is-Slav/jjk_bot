from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List
from utils.card_rewards import is_character_template, is_support_template

def get_card_list_keyboard(cards: List, page: int = 0, cards_per_page: int = 5):
    """Клавиатура списка карт с пагинацией"""
    buttons = []
    
    # Карты на текущей странице
    start = page * cards_per_page
    end = start + cards_per_page
    page_cards = cards[start:end]
    
    for card in page_cards:
        card_name = card.card_template.name if card.card_template else "Unknown"
        rarity_emoji = {
            "common": "⚪",
            "rare": "🔵",
            "epic": "🟣",
            "legendary": "🟡",
            "mythical": "🔴"
        }.get(card.card_template.rarity, "⚪") if card.card_template else "⚪"
        
        buttons.append([
            InlineKeyboardButton(
                text=f"{rarity_emoji} {card_name} (Lv.{card.level})",
                callback_data=f"card_detail_{card.id}"
            )
        ])
    
    # Кнопки пагинации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"cards_page_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📄 {page+1}", callback_data="noop"))
    if end < len(cards):
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"cards_page_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    # Кнопка назад
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="inventory")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_card_detail_keyboard(card_id: int, is_equipped: bool = False, can_upgrade: bool = True):
    """Клавиатура деталей карты"""
    buttons = []
    
    if not is_equipped:
        buttons.append([
            InlineKeyboardButton(text="🎒 Экипировать", callback_data=f"equip_card_{card_id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="❌ Снять", callback_data=f"unequip_card_{card_id}")
        ])
    
    if can_upgrade:
        buttons.append([
            InlineKeyboardButton(text="⬆️ Прокачать", callback_data=f"upgrade_card_{card_id}")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="all_cards")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_upgrade_keyboard(card_id: int, cost: int, player_points: int):
    """Клавиатура прокачки карты"""
    can_upgrade = player_points >= cost
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"⬆️ Прокачать ({cost} очков)" if can_upgrade else f"❌ Недостаточно очков ({cost})",
                callback_data=f"confirm_upgrade_{card_id}" if can_upgrade else "noop"
            )
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data=f"card_detail_{card_id}")
        ]
    ])
    return keyboard

def get_deck_keyboard(main_card=None, support_card=None):
    """Клавиатура управления колодой"""
    buttons = []
    
    if main_card:
        card_name = main_card.card_template.name if main_card.card_template else "Unknown"
        buttons.append([
            InlineKeyboardButton(text=f"👑 Главная: {card_name}", callback_data=f"card_detail_{main_card.id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="➕ Выбрать главную карту", callback_data="select_main_card")
        ])
    
    if support_card:
        card_name = support_card.card_template.name if support_card.card_template else "Unknown"
        buttons.append([
            InlineKeyboardButton(text=f"🛡️ Поддержка: {card_name}", callback_data=f"card_detail_{support_card.id}")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="➕ Выбрать карту поддержки", callback_data="select_support_card")
        ])
    
    buttons.append([
        InlineKeyboardButton(text="🔙 Назад", callback_data="profile")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_card_selection_keyboard(cards: List, slot_type: str = "main", page: int = 0):
    """Клавиатура выбора карты для колоды"""
    buttons = []
    cards_per_page = 5
    
    # Фильтруем карты по типу
    if slot_type == "main":
        filtered_cards = [c for c in cards if c.card_template and is_character_template(c.card_template)]
    else:
        filtered_cards = [c for c in cards if c.card_template and is_support_template(c.card_template)]
    
    start = page * cards_per_page
    end = start + cards_per_page
    page_cards = filtered_cards[start:end]
    
    for card in page_cards:
        card_name = card.card_template.name if card.card_template else "Unknown"
        buttons.append([
            InlineKeyboardButton(
                text=f"{card_name} (Lv.{card.level})",
                callback_data=f"select_card_{slot_type}_{card.id}"
            )
        ])
    
    # Пагинация
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️", callback_data=f"select_page_{slot_type}_{page-1}"))
    if end < len(filtered_cards):
        nav_buttons.append(InlineKeyboardButton(text="▶️", callback_data=f"select_page_{slot_type}_{page+1}"))
    
    if nav_buttons:
        buttons.append(nav_buttons)
    
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="my_deck")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)
