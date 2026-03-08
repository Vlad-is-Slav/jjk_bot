from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_pve_menu():
    """Меню PvE арены"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔰 Легкая арена", callback_data="pve_easy"),
            InlineKeyboardButton(text="⚔️ Средняя арена", callback_data="pve_medium")
        ],
        [
            InlineKeyboardButton(text="👹 Сложная арена", callback_data="pve_hard"),
            InlineKeyboardButton(text="💀 Катастрофа", callback_data="pve_disaster")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="battle_menu")
        ]
    ])
    return keyboard

def get_pve_battle_keyboard(can_flee: bool = True):
    """Клавиатура во время PvE боя"""
    buttons = [
        [
            InlineKeyboardButton(text="⚔️ Атаковать", callback_data="pve_attack"),
            InlineKeyboardButton(text="🛡️ Защищаться", callback_data="pve_defend")
        ]
    ]
    
    if can_flee:
        buttons.append([
            InlineKeyboardButton(text="🏃 Сбежать", callback_data="pve_flee")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_pve_result_keyboard(won: bool, can_continue: bool = True):
    """Клавиатура результата PvE боя"""
    buttons = []
    
    if won and can_continue:
        buttons.append([
            InlineKeyboardButton(text="⚔️ Следующий бой", callback_data="pve_next"),
            InlineKeyboardButton(text="🔙 В меню", callback_data="pve_arena")
        ])
    else:
        buttons.append([
            InlineKeyboardButton(text="🔙 В меню арены", callback_data="pve_arena")
        ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)