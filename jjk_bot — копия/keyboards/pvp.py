from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_pvp_menu():
    """Меню PvP."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔍 Найти соперника", callback_data="pvp_find"),
            InlineKeyboardButton(text="🎯 Вызвать игрока", callback_data="pvp_challenge"),
        ],
        [
            InlineKeyboardButton(text="📜 История PvP", callback_data="pvp_history"),
            InlineKeyboardButton(text="🔙 Назад", callback_data="battle_menu"),
        ],
    ])


def get_pvp_search_keyboard():
    """Клавиатура поиска соперника."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Искать снова", callback_data="pvp_find"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="pvp_menu"),
        ]
    ])


def get_pvp_waiting_keyboard():
    """Клавиатура ожидания real-time соперника."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Обновить поиск", callback_data="pvp_find"),
            InlineKeyboardButton(text="❌ Отменить поиск", callback_data="pvp_cancel_search"),
        ]
    ])


def get_pvp_challenge_keyboard(target_id: int):
    """Клавиатура вызова на бой."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚔️ Принять", callback_data=f"pvp_accept_{target_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"pvp_decline_{target_id}"),
        ]
    ])


def get_pvp_challenge_input_keyboard():
    """Клавиатура ввода цели для прямого вызова."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="❌ Отмена", callback_data="pvp_cancel_challenge_input"),
            InlineKeyboardButton(text="🔙 В PvP меню", callback_data="pvp_menu"),
        ]
    ])


def get_pvp_battle_keyboard(is_your_turn: bool = True, fighter_state: dict | None = None):
    """Клавиатура PvP во время боя."""
    if not is_your_turn:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏳ Ход соперника...", callback_data="noop")]
        ])

    rows = [
        [InlineKeyboardButton(text="👊 Удар рукой", callback_data="pvp_action_basic")]
    ]

    specials = (fighter_state or {}).get("specials", [])
    for special in specials:
        rows.append([
            InlineKeyboardButton(
                text=f"{special['icon']} {special['name']} ({special['ce_cost']} CE)",
                callback_data=f"pvp_action_special_{special['key']}",
            )
        ])

    utility_buttons = []
    if fighter_state and fighter_state.get("has_domain"):
        utility_buttons.append(
            InlineKeyboardButton(
                text=f"🏯 Расширение ({fighter_state.get('domain_cost', 4000)} CE)",
                callback_data="pvp_action_domain",
            )
        )
    if fighter_state and fighter_state.get("has_simple_domain"):
        utility_buttons.append(
            InlineKeyboardButton(
                text=f"🛡 Простая тер. ({fighter_state.get('simple_domain_cost', 1500)} CE)",
                callback_data="pvp_action_simple",
            )
        )
    if fighter_state and fighter_state.get("has_reverse_ct"):
        utility_buttons.append(
            InlineKeyboardButton(
                text=f"♻️ ОПТ ({fighter_state.get('rct_cost', 2500)} CE)",
                callback_data="pvp_action_rct",
            )
        )

    if utility_buttons:
        rows.append(utility_buttons[:2])
        if len(utility_buttons) > 2:
            rows.append(utility_buttons[2:])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def get_pvp_result_keyboard(won: bool):
    """Клавиатура результата PvP."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Реванш", callback_data="pvp_rematch"),
            InlineKeyboardButton(text="🔙 В меню PvP", callback_data="pvp_menu"),
        ],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")],
    ])
