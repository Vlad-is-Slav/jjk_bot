from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_pvp_menu():
    """Меню PvP"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Найти соперника", callback_data="pvp_find"),
            InlineKeyboardButton(text="🎯 Вызвать игрока", callback_data="pvp_challenge")
        ],
        [
            InlineKeyboardButton(text="📜 История PvP", callback_data="pvp_history"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="battle_menu")
        ]
    ])
    return keyboard

def get_pvp_search_keyboard():
    """Клавиатура поиска соперника"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Искать снова", callback_data="pvp_find"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="pvp_menu")
        ]
    ])
    return keyboard

def get_pvp_challenge_keyboard(target_id: int):
    """Клавиатура вызова на бой"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔️ Принять вызов", callback_data=f"pvp_accept_{target_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"pvp_decline_{target_id}")
        ]
    ])
    return keyboard

def get_pvp_battle_keyboard(is_your_turn: bool = True):
    """Клавиатура во время PvP боя"""
    if is_your_turn:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⚔️ Атаковать", callback_data="pvp_attack"),
                InlineKeyboardButton(text="🛡️ Защищаться", callback_data="pvp_defend")
            ],
            [
                InlineKeyboardButton(text="💥 Специальная атака", callback_data="pvp_special")
            ]
        ])
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⏳ Ожидание хода соперника...", callback_data="noop")
            ]
        ])
    return keyboard

def get_pvp_result_keyboard(won: bool):
    """Клавиатура результата PvP боя"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Реванш", callback_data="pvp_rematch"),
            InlineKeyboardButton(text="🔙 В меню PvP", callback_data="pvp_menu")
        ],
        [
            InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")
        ]
    ])
    return keyboard