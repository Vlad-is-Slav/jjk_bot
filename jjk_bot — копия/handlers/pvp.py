import random
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from models import async_session, User, UserCard, Battle
from keyboards.pvp import (
    get_pvp_menu,
    get_pvp_waiting_keyboard,
    get_pvp_challenge_keyboard,
    get_pvp_challenge_input_keyboard,
    get_pvp_battle_keyboard,
    get_pvp_result_keyboard,
)
from utils.daily_quest_progress import add_daily_quest_progress
from utils.pvp_progression import apply_experience_with_pvp_rolls, get_player_pvp_toolkit

router = Router()

# Хранилище активных PvP боев
active_pvp_battles = {}
pvp_matchmaking_queue = {}  # telegram_id -> {"joined_at": datetime, "user_id": int, "level": int}
pvp_challenges = {}  # (challenger_tg, accepter_tg) -> created_at
pvp_challenge_target_input = {}  # telegram_id -> created_at


DEFAULT_DOMAIN_DURATION = 3
DEFAULT_SIMPLE_DOMAIN_DURATION = 2
PVP_COOLDOWN_SECONDS = 120
PVP_MATCHMAKING_TIMEOUT = timedelta(minutes=3)
PVP_CHALLENGE_INPUT_TIMEOUT = timedelta(minutes=5)


CHARACTER_PROFILES = [
    {
        "tokens": ["годжо", "gojo", "satoru"],
        "domain_name": "Безграничная Пустота",
        "domain_dot_pct": 0.15,
        "domain_damage_bonus": 0.30,
        "specials": [
            {"key": "blue", "name": "Синий", "icon": "🔵", "ce_cost": 700, "multiplier": 1.25, "flat": 120},
            {"key": "red", "name": "Красный", "icon": "🔴", "ce_cost": 1000, "multiplier": 1.55, "flat": 220},
            {"key": "purple", "name": "Фиолетовый", "icon": "🟣", "ce_cost": 5000, "multiplier": 2.6, "flat": 500},
        ],
    },
    {
        "tokens": ["сукуна", "sukuna", "ryomen"],
        "domain_name": "Храм Злобы",
        "domain_dot_pct": 0.14,
        "domain_damage_bonus": 0.28,
        "specials": [
            {"key": "cleave", "name": "Рассечение", "icon": "🗡", "ce_cost": 900, "multiplier": 1.45, "flat": 180},
            {"key": "dismantle", "name": "Расщепление", "icon": "⚔️", "ce_cost": 1300, "multiplier": 1.7, "flat": 260},
            {"key": "fuga", "name": "Фуга", "icon": "🔥", "ce_cost": 4500, "multiplier": 2.45, "flat": 520},
        ],
    },
]


DEFAULT_PROFILE = {
    "domain_name": "Расширение территории",
    "domain_dot_pct": 0.10,
    "domain_damage_bonus": 0.20,
    "specials": [
        {"key": "burst", "name": "Выброс CE", "icon": "💥", "ce_cost": 900, "multiplier": 1.35, "flat": 150},
    ],
}


def _find_battle_by_user_tg(telegram_id: int):
    direct = active_pvp_battles.get(telegram_id)
    if direct:
        return direct

    for battle in active_pvp_battles.values():
        if battle["player1_tg"] == telegram_id or battle["player2_tg"] == telegram_id:
            return battle
    return None


def _remove_from_matchmaking_queue(*telegram_ids: int):
    for telegram_id in telegram_ids:
        pvp_matchmaking_queue.pop(telegram_id, None)


def _cleanup_matchmaking_queue():
    now = datetime.utcnow()
    stale_ids = []
    for telegram_id, payload in pvp_matchmaking_queue.items():
        joined_at = payload.get("joined_at", now)
        if now - joined_at > PVP_MATCHMAKING_TIMEOUT:
            stale_ids.append(telegram_id)
            continue
        if _find_battle_by_user_tg(telegram_id):
            stale_ids.append(telegram_id)

    for telegram_id in stale_ids:
        pvp_matchmaking_queue.pop(telegram_id, None)


def _matchmaking_candidate_tgs(user: User) -> list[int]:
    waiting_players = [
        (telegram_id, payload)
        for telegram_id, payload in pvp_matchmaking_queue.items()
        if telegram_id != user.telegram_id
    ]
    waiting_players.sort(key=lambda item: item[1].get("joined_at", datetime.utcnow()))

    ordered = []
    used = set()
    for level_range in (5, 10, None):
        for telegram_id, payload in waiting_players:
            if telegram_id in used:
                continue
            level_diff = abs(payload.get("level", user.level) - user.level)
            if level_range is not None and level_diff > level_range:
                continue
            used.add(telegram_id)
            ordered.append(telegram_id)
    return ordered


def _get_pvp_cooldown_seconds_left(user: User) -> int:
    if not user.last_battle_time:
        return 0
    elapsed = (datetime.utcnow() - user.last_battle_time).total_seconds()
    remaining = int(PVP_COOLDOWN_SECONDS - elapsed)
    return max(0, remaining)


def _cleanup_challenge_input():
    now = datetime.utcnow()
    expired = [
        telegram_id
        for telegram_id, created_at in pvp_challenge_target_input.items()
        if now - created_at > PVP_CHALLENGE_INPUT_TIMEOUT
    ]
    for telegram_id in expired:
        pvp_challenge_target_input.pop(telegram_id, None)


async def _find_user_by_target(session, target_raw: str) -> User | None:
    raw = (target_raw or "").strip()
    if not raw:
        return None

    if raw.startswith("@"):
        username = raw[1:].strip().lower()
        if not username:
            return None
        result = await session.execute(
            select(User).where(func.lower(User.username) == username)
        )
        return result.scalar_one_or_none()

    if raw.isdigit():
        result = await session.execute(
            select(User).where(User.telegram_id == int(raw))
        )
        return result.scalar_one_or_none()

    result = await session.execute(
        select(User).where(func.lower(User.username) == raw.lower())
    )
    return result.scalar_one_or_none()


async def _send_direct_challenge(bot, challenger: User, target: User) -> tuple[bool, str]:
    if challenger.telegram_id == target.telegram_id:
        return False, "Нельзя вызвать самого себя."

    if _find_battle_by_user_tg(challenger.telegram_id) or _find_battle_by_user_tg(target.telegram_id):
        return False, "Один из игроков уже находится в PvP бою."

    challenger_cd = _get_pvp_cooldown_seconds_left(challenger)
    if challenger_cd > 0:
        return False, f"Подожди {challenger_cd} сек. перед следующим PvP боем."

    target_cd = _get_pvp_cooldown_seconds_left(target)
    if target_cd > 0:
        return False, "У выбранного игрока ещё не прошёл PvP-кулдаун."

    if not challenger.slot_1_card_id:
        return False, "У тебя не экипирована главная карта."
    if not target.slot_1_card_id:
        return False, "У выбранного игрока не экипирована главная карта."

    key = (challenger.telegram_id, target.telegram_id)
    pvp_challenges[key] = datetime.utcnow()

    challenger_name = challenger.first_name or challenger.username or "Игрок"
    try:
        await bot.send_message(
            target.telegram_id,
            "⚔️ <b>Тебя вызвали на PvP бой!</b>\n\n"
            f"{challenger_name} отправил тебе прямой вызов.\n"
            "Нажми «Принять», чтобы начать бой.",
            reply_markup=get_pvp_challenge_keyboard(challenger.telegram_id),
            parse_mode="HTML",
        )
    except Exception:
        pvp_challenges.pop(key, None)
        return False, "Не удалось отправить вызов игроку. Возможно, он не писал боту."

    return True, f"Вызов отправлен игроку {target.first_name or target.username or target.telegram_id}."


async def _process_direct_challenge_request(message: Message, target_raw: str):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        challenger = result.scalar_one_or_none()
        if not challenger:
            await message.answer("Сначала используй /start")
            return

        target = await _find_user_by_target(session, target_raw)
        if not target:
            await message.answer("Игрок не найден. Укажи корректный @username или telegram_id.")
            return

        ok, response_text = await _send_direct_challenge(message.bot, challenger, target)
        await message.answer(response_text)


def _normalize_name(value: str) -> str:
    return "".join(ch.lower() for ch in (value or "") if ch.isalnum())


def _get_character_profile(card_name: str) -> dict:
    normalized = _normalize_name(card_name)
    for profile in CHARACTER_PROFILES:
        if any(token in normalized for token in profile["tokens"]):
            return profile
    return DEFAULT_PROFILE


def _player_num_by_tg(battle: dict, tg_id: int) -> int:
    return 1 if battle["player1_tg"] == tg_id else 2


def _enemy_num(player_num: int) -> int:
    return 2 if player_num == 1 else 1


def _is_user_turn(battle: dict, tg_id: int) -> bool:
    return battle["current_player"] == _player_num_by_tg(battle, tg_id)


def _get_base_damage(state: dict) -> int:
    damage = state["main"].attack
    if state.get("support"):
        damage += state["support"].attack // 2
    return max(1, damage)


def _domain_attack_bonus(battle: dict, attacker_num: int) -> float:
    domain = battle.get("domain_state")
    if not domain or domain["owner"] != attacker_num:
        return 1.0
    return 1.0 + domain.get("damage_bonus", 0.0)


def _deal_damage(battle: dict, attacker_num: int, defender_num: int, raw_damage: int) -> int:
    attacker_bonus = _domain_attack_bonus(battle, attacker_num)
    final_raw = max(1, int(raw_damage * attacker_bonus))
    defender = battle["fighters"][defender_num]["main"]
    return defender.take_damage(final_raw)


def _domain_power(state: dict) -> int:
    main = state["main"]
    support = state.get("support")
    support_bonus = (support.attack + support.defense) // 3 if support else 0
    return (
        main.attack
        + main.defense
        + main.speed
        + support_bonus
        + main.level * 25
        + random.randint(0, 120)
    )


def _spend_ce(state: dict, amount: int) -> bool:
    if state["ce"] < amount:
        return False
    state["ce"] -= amount
    return True


def _format_fighter_line(prefix: str, state: dict) -> str:
    simple_left = state.get("simple_domain_turns", 0)
    simple_text = f" | 🛡 {simple_left}х" if simple_left > 0 else ""
    return (
        f"{prefix} {state['main'].card_template.name}\n"
        f"❤️ {state['main'].hp}/{state['main'].max_hp} | "
        f"💧 {state['ce']}/{state['max_ce']}{simple_text}\n"
    )


def _battle_view_text(battle: dict, viewer_tg: int) -> str:
    viewer_num = _player_num_by_tg(battle, viewer_tg)
    enemy_num = _enemy_num(viewer_num)
    you = battle["fighters"][viewer_num]
    enemy = battle["fighters"][enemy_num]

    text = (
        f"⚔️ <b>PvP бой — ход {battle['turn']}</b>\n\n"
        f"<b>Ты:</b>\n{_format_fighter_line('🃏', you)}\n"
        f"<b>Противник:</b>\n{_format_fighter_line('🃏', enemy)}"
    )

    domain = battle.get("domain_state")
    if domain:
        owner_num = domain["owner"]
        owner_name = battle["fighters"][owner_num]["main"].card_template.name
        text += (
            f"\n🏯 <b>Активная территория:</b> {domain['name']}\n"
            f"Владелец: {owner_name} | Осталось: {domain['turns_left']}х"
        )

    if battle["log"]:
        last_logs = battle["log"][-5:]
        text += "\n\n<b>Последние события:</b>\n" + "\n".join(f"• {line}" for line in last_logs)

    text += "\n\n⚡ <b>Твой ход!</b>" if battle["current_player"] == viewer_num else "\n⏳ <b>Ход соперника...</b>"
    return text


async def _edit_or_send_battle_message(callback: CallbackQuery, telegram_id: int, battle: dict):
    viewer_num = _player_num_by_tg(battle, telegram_id)
    is_your_turn = battle["current_player"] == viewer_num
    text = _battle_view_text(battle, telegram_id)
    keyboard = get_pvp_battle_keyboard(is_your_turn=is_your_turn, fighter_state=battle["fighters"][viewer_num])
    existing_id = battle["messages"].get(telegram_id)

    if callback.from_user.id == telegram_id and callback.message:
        try:
            edited = await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            battle["messages"][telegram_id] = edited.message_id
            return edited
        except Exception:
            pass

    if existing_id:
        try:
            edited = await callback.bot.edit_message_text(
                chat_id=telegram_id,
                message_id=existing_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML",
            )
            if hasattr(edited, "message_id"):
                battle["messages"][telegram_id] = edited.message_id
            return edited
        except Exception:
            pass

    try:
        sent = await callback.bot.send_message(
            telegram_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
        battle["messages"][telegram_id] = sent.message_id
        return sent
    except Exception:
        return None


async def _update_battle_messages(callback: CallbackQuery, battle: dict):
    await _edit_or_send_battle_message(callback, battle["player1_tg"], battle)
    await _edit_or_send_battle_message(callback, battle["player2_tg"], battle)


def _apply_start_turn_effects(battle: dict, player_num: int):
    state = battle["fighters"][player_num]

    # Реген CE
    state["ce"] = min(state["max_ce"], state["ce"] + state["ce_regen"])

    simple_active = state.get("simple_domain_turns", 0) > 0
    domain = battle.get("domain_state")

    if domain and domain["target"] == player_num:
        if simple_active:
            battle["log"].append("🛡 Простая территория блокирует эффект вражеской территории.")
        else:
            owner_state = battle["fighters"][domain["owner"]]
            raw = int(state["main"].max_hp * domain["dot_pct"]) + int(owner_state["main"].attack * 0.25)
            dealt = state["main"].take_damage(max(1, raw))
            battle["log"].append(f"🏯 {domain['name']} наносит {dealt} урона.")
            domain["turns_left"] -= 1
            if domain["turns_left"] <= 0:
                battle["log"].append("🌫 Эффект территории рассеялся.")
                battle["domain_state"] = None

    if simple_active:
        state["simple_domain_turns"] -= 1
        if state["simple_domain_turns"] == 0:
            battle["log"].append("🛡 Простая территория закончилась.")


async def _advance_turn(callback: CallbackQuery, battle: dict, acting_player_num: int):
    next_player = _enemy_num(acting_player_num)
    battle["current_player"] = next_player
    battle["turn"] += 1

    _apply_start_turn_effects(battle, next_player)
    if not battle["fighters"][next_player]["main"].is_alive():
        await end_pvp_battle(callback, battle, winner_is_player1=acting_player_num == 1)
        return

    await _update_battle_messages(callback, battle)


def _action_basic_attack(battle: dict, attacker_num: int):
    attacker = battle["fighters"][attacker_num]
    defender_num = _enemy_num(attacker_num)
    defender = battle["fighters"][defender_num]

    base_damage = _get_base_damage(attacker)
    black_flash = random.random() < attacker["black_flash_chance"]

    if black_flash:
        base_damage = int(base_damage * 2.2)

    dealt = _deal_damage(battle, attacker_num, defender_num, base_damage)
    if black_flash:
        heal_amount = int(attacker["main"].max_hp * 0.08)
        attacker["main"].hp = min(attacker["main"].max_hp, attacker["main"].hp + heal_amount)
        battle["log"].append(
            f"⚫ Чёрная молния! Урон: {dealt}, восстановлено HP: {heal_amount}."
        )
    else:
        battle["log"].append(f"👊 Обычная атака наносит {dealt} урона.")

    return defender["main"].is_alive()


def _action_special(battle: dict, attacker_num: int, key: str):
    attacker = battle["fighters"][attacker_num]
    defender_num = _enemy_num(attacker_num)
    defender = battle["fighters"][defender_num]

    if attacker.get("simple_domain_turns", 0) > 0:
        return False, "Во время простой территории нельзя использовать спецтехники."

    special = next((sp for sp in attacker["specials"] if sp["key"] == key), None)
    if not special:
        return False, "Эта техника недоступна для твоей карты."

    if not _spend_ce(attacker, special["ce_cost"]):
        return False, "Недостаточно CE для этой техники."

    raw = int(_get_base_damage(attacker) * special["multiplier"] + special.get("flat", 0))
    dealt = _deal_damage(battle, attacker_num, defender_num, raw)
    battle["log"].append(
        f"{special['icon']} {special['name']} наносит {dealt} урона "
        f"(-{special['ce_cost']} CE)."
    )
    return defender["main"].is_alive(), None


def _action_domain(battle: dict, attacker_num: int):
    attacker = battle["fighters"][attacker_num]
    defender_num = _enemy_num(attacker_num)
    defender = battle["fighters"][defender_num]
    cost = attacker["domain_cost"]

    if not attacker.get("has_domain"):
        return False, "У тебя нет техники расширения территории."

    if not _spend_ce(attacker, cost):
        return False, "Недостаточно CE для расширения территории."

    domain = battle.get("domain_state")
    if domain and domain["owner"] == attacker_num:
        attacker["ce"] += cost
        return False, "Твоя территория уже активна."

    if domain and domain["owner"] == defender_num:
        # Битва территорий
        attacker_power = _domain_power(attacker)
        defender_power = _domain_power(defender)

        if attacker_power > defender_power:
            battle["domain_state"] = {
                "owner": attacker_num,
                "target": defender_num,
                "name": attacker["domain_name"],
                "turns_left": DEFAULT_DOMAIN_DURATION,
                "dot_pct": attacker["domain_dot_pct"],
                "damage_bonus": attacker["domain_damage_bonus"],
            }
            battle["log"].append("💥 Битва территорий: ты победил и подавил вражеский домен.")
        elif attacker_power < defender_power:
            battle["log"].append("💥 Битва территорий: твой домен проиграл.")
        else:
            battle["domain_state"] = None
            battle["log"].append("💥 Битва территорий закончилась ничьёй. Оба домена рассеялись.")
        return True, None

    battle["domain_state"] = {
        "owner": attacker_num,
        "target": defender_num,
        "name": attacker["domain_name"],
        "turns_left": DEFAULT_DOMAIN_DURATION,
        "dot_pct": attacker["domain_dot_pct"],
        "damage_bonus": attacker["domain_damage_bonus"],
    }
    battle["log"].append(f"🏯 Активирована территория: {attacker['domain_name']} (-{cost} CE).")
    return True, None


def _action_simple_domain(battle: dict, attacker_num: int):
    attacker = battle["fighters"][attacker_num]
    cost = attacker["simple_domain_cost"]

    if not attacker.get("has_simple_domain"):
        return False, "У тебя нет техники простой территории."
    if attacker.get("simple_domain_turns", 0) > 0:
        return False, "Простая территория уже активна."
    if not _spend_ce(attacker, cost):
        return False, "Недостаточно CE для простой территории."

    attacker["simple_domain_turns"] = DEFAULT_SIMPLE_DOMAIN_DURATION
    battle["log"].append(
        f"🛡 Простая территория активирована на {DEFAULT_SIMPLE_DOMAIN_DURATION} хода "
        f"(-{cost} CE)."
    )
    return True, None


def _action_reverse_ct(battle: dict, attacker_num: int):
    attacker = battle["fighters"][attacker_num]
    cost = attacker["rct_cost"]

    if not attacker.get("has_reverse_ct"):
        return False, "У тебя нет обратной проклятой техники."
    if attacker["main"].hp >= attacker["main"].max_hp:
        return False, "HP уже полное."
    if not _spend_ce(attacker, cost):
        return False, "Недостаточно CE для лечения."

    heal_amount = int(attacker["main"].max_hp * 0.35 + attacker["main"].defense * 0.2)
    before = attacker["main"].hp
    attacker["main"].hp = min(attacker["main"].max_hp, attacker["main"].hp + heal_amount)
    healed = attacker["main"].hp - before
    battle["log"].append(f"♻️ Обратная техника восстановила {healed} HP (-{cost} CE).")
    return True, None


async def _process_action(callback: CallbackQuery, action: str):
    user_id = callback.from_user.id
    battle = _find_battle_by_user_tg(user_id)

    if not battle:
        await callback.answer("Бой не найден.", show_alert=True)
        return

    if not _is_user_turn(battle, user_id):
        await callback.answer("Сейчас не твой ход.", show_alert=True)
        return

    attacker_num = _player_num_by_tg(battle, user_id)
    defender_num = _enemy_num(attacker_num)
    defender_alive = True

    if action == "basic":
        defender_alive = _action_basic_attack(battle, attacker_num)
    elif action.startswith("special_"):
        defender_alive, error = _action_special(battle, attacker_num, action.split("special_", 1)[1])
        if error:
            await callback.answer(error, show_alert=True)
            return
    elif action == "domain":
        ok, error = _action_domain(battle, attacker_num)
        if error:
            await callback.answer(error, show_alert=True)
            return
    elif action == "simple":
        ok, error = _action_simple_domain(battle, attacker_num)
        if error:
            await callback.answer(error, show_alert=True)
            return
    elif action == "rct":
        ok, error = _action_reverse_ct(battle, attacker_num)
        if error:
            await callback.answer(error, show_alert=True)
            return
    else:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    if not defender_alive:
        await end_pvp_battle(callback, battle, winner_is_player1=attacker_num == 1)
        await callback.answer()
        return

    if not battle["fighters"][defender_num]["main"].is_alive():
        await end_pvp_battle(callback, battle, winner_is_player1=attacker_num == 1)
        await callback.answer()
        return

    await _advance_turn(callback, battle, attacker_num)
    await callback.answer()


@router.message(Command("pvp"))
async def cmd_pvp(message: Message):
    _remove_from_matchmaking_queue(message.from_user.id)
    pvp_challenge_target_input.pop(message.from_user.id, None)
    await message.answer(
        "⚔️ <b>PvP Арена</b>\n\nВыбери действие:",
        reply_markup=get_pvp_menu(),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "pvp_menu")
async def pvp_menu_callback(callback: CallbackQuery):
    _remove_from_matchmaking_queue(callback.from_user.id)
    pvp_challenge_target_input.pop(callback.from_user.id, None)
    await callback.message.edit_text(
        "⚔️ <b>PvP Арена</b>\n\n"
        "Сражайся с другими игроками, используй техники карт и побеждай.\n\n"
        "🏆 Победы дают опыт и очки.",
        reply_markup=get_pvp_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "pvp_find")
async def pvp_find_callback(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        if _find_battle_by_user_tg(user.telegram_id):
            await callback.answer("Ты уже участвуешь в PvP бою.", show_alert=True)
            return

        cooldown_left = _get_pvp_cooldown_seconds_left(user)
        if cooldown_left > 0:
            await callback.answer(
                f"Подожди {cooldown_left} сек. перед следующим PvP боем.",
                show_alert=True,
            )
            return

        if not user.slot_1_card_id:
            await callback.answer("У тебя не экипирована главная карта.", show_alert=True)
            return

        _cleanup_matchmaking_queue()

        opponent = None
        for opponent_tg in _matchmaking_candidate_tgs(user):
            if _find_battle_by_user_tg(opponent_tg):
                _remove_from_matchmaking_queue(opponent_tg)
                continue

            result = await session.execute(select(User).where(User.telegram_id == opponent_tg))
            candidate = result.scalar_one_or_none()
            if not candidate or not candidate.slot_1_card_id:
                _remove_from_matchmaking_queue(opponent_tg)
                continue

            if _get_pvp_cooldown_seconds_left(candidate) > 0:
                _remove_from_matchmaking_queue(opponent_tg)
                continue

            opponent = candidate
            break

        if opponent:
            _remove_from_matchmaking_queue(user.telegram_id, opponent.telegram_id)
            started = await start_pvp_battle(callback, user, opponent)
            if started:
                await callback.answer("Соперник найден! Бой начался.")
            else:
                await callback.answer("Не удалось запустить бой. Попробуй поиск ещё раз.", show_alert=True)
            return

        existing = pvp_matchmaking_queue.get(user.telegram_id, {})
        joined_at = existing.get("joined_at", datetime.utcnow())
        pvp_matchmaking_queue[user.telegram_id] = {
            "joined_at": joined_at,
            "user_id": user.id,
            "level": user.level,
        }

        wait_seconds = int((datetime.utcnow() - joined_at).total_seconds())
        opponents_waiting = max(0, len(pvp_matchmaking_queue) - 1)

        waiting_text = (
            "🔎 <b>Поиск PvP соперника</b>\n\n"
            "Матчмейкинг ищет игрока, который тоже прямо сейчас нажал поиск.\n\n"
            f"👥 В очереди сейчас: {opponents_waiting}\n"
            f"⏱ Время ожидания: {wait_seconds} сек.\n\n"
            "Бой начнётся автоматически, как только найдётся второй реальный игрок."
        )
        try:
            await callback.message.edit_text(
                waiting_text,
                reply_markup=get_pvp_waiting_keyboard(),
                parse_mode="HTML",
            )
        except Exception:
            await callback.bot.send_message(
                callback.from_user.id,
                waiting_text,
                reply_markup=get_pvp_waiting_keyboard(),
                parse_mode="HTML",
            )
        await callback.answer("Ты добавлен в очередь поиска.")


@router.callback_query(F.data == "pvp_cancel_search")
async def pvp_cancel_search_callback(callback: CallbackQuery):
    removed = callback.from_user.id in pvp_matchmaking_queue
    _remove_from_matchmaking_queue(callback.from_user.id)

    cancel_text = (
        "⚔️ <b>PvP Арена</b>\n\n"
        "Поиск соперника отменён.\n\n"
        "Нажми «Найти соперника», чтобы снова встать в очередь."
    )
    try:
        await callback.message.edit_text(
            cancel_text,
            reply_markup=get_pvp_menu(),
            parse_mode="HTML",
        )
    except Exception:
        await callback.bot.send_message(
            callback.from_user.id,
            cancel_text,
            reply_markup=get_pvp_menu(),
            parse_mode="HTML",
        )
    await callback.answer("Поиск отменён." if removed else "Ты не находился в поиске.")


async def _load_card(session, card_id: int):
    if not card_id:
        return None
    result = await session.execute(
        select(UserCard)
        .options(selectinload(UserCard.card_template))
        .where(UserCard.id == card_id)
    )
    return result.scalar_one_or_none()


def _build_fighter_state(main_card: UserCard, support_card: UserCard | None, toolkit: dict):
    profile = _get_character_profile(main_card.card_template.name if main_card.card_template else "")
    support_ce_bonus = support_card.max_ce * 30 if support_card else 0

    max_ce = max(3000, main_card.max_ce * 100 + support_ce_bonus)
    ce_regen = max(300, (main_card.card_template.ce_regen if main_card.card_template else 10) * 100)

    return {
        "main": main_card,
        "support": support_card,
        "specials": profile["specials"],
        "domain_name": profile["domain_name"],
        "domain_dot_pct": profile["domain_dot_pct"],
        "domain_damage_bonus": profile["domain_damage_bonus"],
        "ce": max_ce,
        "max_ce": max_ce,
        "ce_regen": ce_regen,
        "has_domain": toolkit.get("has_domain", False),
        "has_simple_domain": toolkit.get("has_simple_domain", False),
        "has_reverse_ct": toolkit.get("has_reverse_ct", False),
        "domain_cost": 4000,
        "simple_domain_cost": 1500,
        "rct_cost": 2500,
        "simple_domain_turns": 0,
        "black_flash_chance": 0.10,
    }


async def start_pvp_battle(callback: CallbackQuery, player1: User, player2: User, is_rematch: bool = False) -> bool:
    async with async_session() as session:
        _remove_from_matchmaking_queue(player1.telegram_id, player2.telegram_id)

        p1_main = await _load_card(session, player1.slot_1_card_id)
        p1_support = await _load_card(session, player1.slot_2_card_id)
        p2_main = await _load_card(session, player2.slot_1_card_id)
        p2_support = await _load_card(session, player2.slot_2_card_id)

        if not p1_main or not p2_main:
            await callback.answer("У одного из игроков не экипирована главная карта.", show_alert=True)
            return False

        p1_main.heal()
        p2_main.heal()
        if p1_support:
            p1_support.heal()
        if p2_support:
            p2_support.heal()

        p1_toolkit = await get_player_pvp_toolkit(session, player1.id)
        p2_toolkit = await get_player_pvp_toolkit(session, player2.id)

        battle_id = f"pvp_{player1.id}_{player2.id}_{datetime.utcnow().timestamp()}"
        current_player = 1

        p1_speed = p1_main.speed + (p1_support.speed if p1_support else 0)
        p2_speed = p2_main.speed + (p2_support.speed if p2_support else 0)
        if p2_speed > p1_speed:
            current_player = 2
        first_turn_card = p1_main.card_template.name if current_player == 1 else p2_main.card_template.name

        battle = {
            "battle_id": battle_id,
            "player1_id": player1.id,
            "player1_tg": player1.telegram_id,
            "player2_id": player2.id,
            "player2_tg": player2.telegram_id,
            "fighters": {
                1: _build_fighter_state(p1_main, p1_support, p1_toolkit),
                2: _build_fighter_state(p2_main, p2_support, p2_toolkit),
            },
            "turn": 1,
            "current_player": current_player,
            "domain_state": None,
            "log": [
                f"⚡ Первый ход за картой {first_turn_card} (преимущество скорости)."
            ],
            "messages": {},
        }
        active_pvp_battles[player1.telegram_id] = battle
        active_pvp_battles[player2.telegram_id] = battle

        await _update_battle_messages(callback, battle)
        return True


@router.callback_query(F.data.startswith("pvp_action_"))
async def pvp_action_callback(callback: CallbackQuery):
    action = callback.data.split("pvp_action_", 1)[1]
    await _process_action(callback, action)


# Legacy callbacks from old keyboards
@router.callback_query(F.data == "pvp_attack")
async def legacy_pvp_attack_callback(callback: CallbackQuery):
    await _process_action(callback, "basic")


@router.callback_query(F.data == "pvp_special")
async def legacy_pvp_special_callback(callback: CallbackQuery):
    await callback.answer("Теперь спецтехники выбираются отдельными кнопками в PvP.", show_alert=True)


@router.callback_query(F.data == "pvp_defend")
async def legacy_pvp_defend_callback(callback: CallbackQuery):
    await callback.answer("Защита удалена из PvP. Используй Простую территорию или ОПТ.", show_alert=True)


async def end_pvp_battle(callback: CallbackQuery, battle: dict, winner_is_player1: bool):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.id == battle["player1_id"]))
        player1 = result.scalar_one()
        result = await session.execute(select(User).where(User.id == battle["player2_id"]))
        player2 = result.scalar_one()

        winner = player1 if winner_is_player1 else player2
        loser = player2 if winner_is_player1 else player1

        winner.pvp_wins += 1
        winner.total_battles += 1
        winner.last_battle_time = datetime.utcnow()
        await add_daily_quest_progress(session, winner.id, "pvp_wins", amount=1)
        await add_daily_quest_progress(session, winner.id, "pvp_battles", amount=1)

        loser.pvp_losses += 1
        loser.total_battles += 1
        loser.last_battle_time = datetime.utcnow()
        await add_daily_quest_progress(session, loser.id, "pvp_battles", amount=1)

        exp_gained = 50
        points_gained = 5

        level_diff = loser.level - winner.level
        if level_diff > 0:
            exp_gained += level_diff * 10
            points_gained += level_diff

        leveled_up, actual_exp, unlocked_from_level = await apply_experience_with_pvp_rolls(
            session, winner, exp_gained
        )
        winner.points += points_gained

        await session.commit()

        battle_record = Battle(
            battle_type="pvp",
            player1_id=player1.id,
            player2_id=player2.id,
            winner_id=winner.id,
            battle_log="\n".join(battle["log"]),
            exp_gained=actual_exp,
            points_gained=points_gained,
        )
        session.add(battle_record)
        await session.commit()

        winner_text = (
            f"🏆 <b>Победа!</b>\n\n"
            f"Ты победил {loser.first_name or 'противника'}!\n\n"
            f"⭐ Опыт: +{actual_exp}\n"
            f"💎 Очки: +{points_gained}\n"
        )
        if leveled_up:
            winner_text += f"🎉 <b>Новый уровень! Теперь ты {winner.level} уровня!</b>\n"
        if unlocked_from_level:
            unlocked_names = ", ".join(t.name for t in unlocked_from_level)
            winner_text += f"✨ <b>Новые PvP-техники:</b> {unlocked_names}\n"

        loser_text = (
            f"💀 <b>Поражение...</b>\n\n"
            f"{winner.first_name or 'Противник'} оказался сильнее.\n\n"
            f"Прокачай карты и попробуй снова."
        )

        try:
            await callback.bot.send_message(
                winner.telegram_id,
                winner_text,
                reply_markup=get_pvp_result_keyboard(True),
                parse_mode="HTML",
            )
        except Exception:
            pass

        try:
            await callback.bot.send_message(
                loser.telegram_id,
                loser_text,
                reply_markup=get_pvp_result_keyboard(False),
                parse_mode="HTML",
            )
        except Exception:
            pass

    for uid, existing in list(active_pvp_battles.items()):
        if existing["battle_id"] == battle["battle_id"]:
            del active_pvp_battles[uid]


@router.callback_query(F.data == "pvp_history")
async def pvp_history_callback(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == callback.from_user.id))
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        result = await session.execute(
            select(Battle)
            .options(
                selectinload(Battle.player1),
                selectinload(Battle.player2),
            )
            .where(
                Battle.battle_type == "pvp",
                (Battle.player1_id == user.id) | (Battle.player2_id == user.id),
            )
            .order_by(Battle.created_at.desc())
            .limit(10)
        )
        battles = result.scalars().all()

        if not battles:
            await callback.message.edit_text(
                "📜 <b>История PvP</b>\n\nУ тебя пока нет PvP-боёв.",
                reply_markup=get_pvp_menu(),
                parse_mode="HTML",
            )
            return

        history_text = "📜 <b>Последние PvP бои:</b>\n\n"
        for i, item in enumerate(battles, 1):
            opponent_name = item.get_opponent_name(user.id)
            is_winner = item.winner_id == user.id
            result_emoji = "🏆" if is_winner else "💀"
            history_text += f"{i}. {result_emoji} vs {opponent_name}\n"

        from keyboards.main_menu import get_back_button

        await callback.message.edit_text(
            history_text,
            reply_markup=get_back_button("pvp_menu"),
            parse_mode="HTML",
        )
    await callback.answer()


@router.callback_query(F.data == "pvp_challenge")
async def pvp_challenge_callback(callback: CallbackQuery):
    _cleanup_challenge_input()
    pvp_challenge_target_input[callback.from_user.id] = datetime.utcnow()
    await callback.message.edit_text(
        "🎯 <b>Вызов игрока</b>\n\n"
        "Отправь следующим сообщением <b>@username</b> или <b>telegram_id</b> игрока,\n"
        "которому хочешь кинуть вызов.\n\n"
        "Пример:\n"
        "<code>@player_name</code>\n"
        "<code>123456789</code>\n\n"
        "Также можно использовать команду:\n"
        "<code>/challenge @username</code>",
        reply_markup=get_pvp_challenge_input_keyboard(),
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data == "pvp_cancel_challenge_input")
async def pvp_cancel_challenge_input_callback(callback: CallbackQuery):
    pvp_challenge_target_input.pop(callback.from_user.id, None)
    await callback.message.edit_text(
        "⚔️ <b>PvP Арена</b>\n\n"
        "Ввод цели для вызова отменён.",
        reply_markup=get_pvp_menu(),
        parse_mode="HTML",
    )
    await callback.answer("Отменено.")


@router.message(Command("challenge"))
async def challenge_command(message: Message):
    args = message.text.split(maxsplit=1)
    if len(args) < 2 or not args[1].strip():
        await message.answer(
            "Использование:\n"
            "<code>/challenge @username</code>\n"
            "<code>/challenge telegram_id</code>",
            parse_mode="HTML",
        )
        return

    pvp_challenge_target_input.pop(message.from_user.id, None)
    await _process_direct_challenge_request(message, args[1].strip())


@router.message(F.text, ~F.text.startswith("/"))
async def pvp_challenge_target_input_handler(message: Message):
    _cleanup_challenge_input()

    created_at = pvp_challenge_target_input.get(message.from_user.id)
    if not created_at:
        return

    if message.text.strip().startswith("/"):
        pvp_challenge_target_input.pop(message.from_user.id, None)
        return

    pvp_challenge_target_input.pop(message.from_user.id, None)
    await _process_direct_challenge_request(message, message.text.strip())


@router.callback_query(F.data == "pvp_rematch")
async def pvp_rematch_callback(callback: CallbackQuery):
    await pvp_find_callback(callback)


@router.callback_query(F.data.startswith("pvp_accept_"))
async def pvp_accept_callback(callback: CallbackQuery):
    challenger_tg = int(callback.data.split("_")[2])
    accepter_tg = callback.from_user.id
    key = (challenger_tg, accepter_tg)

    created_at = pvp_challenges.get(key)
    if not created_at:
        await callback.answer("Вызов не найден или уже неактуален.", show_alert=True)
        return

    if datetime.utcnow() - created_at > timedelta(minutes=10):
        pvp_challenges.pop(key, None)
        await callback.answer("Вызов истёк. Отправьте новый.", show_alert=True)
        return

    if _find_battle_by_user_tg(challenger_tg) or _find_battle_by_user_tg(accepter_tg):
        pvp_challenges.pop(key, None)
        await callback.answer("Один из игроков уже находится в бою.", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(select(User).where(User.telegram_id == challenger_tg))
        challenger = result.scalar_one_or_none()
        result = await session.execute(select(User).where(User.telegram_id == accepter_tg))
        accepter = result.scalar_one_or_none()

        if not challenger or not accepter:
            pvp_challenges.pop(key, None)
            await callback.answer("Один из игроков не найден.", show_alert=True)
            return

        if not challenger.slot_1_card_id or not accepter.slot_1_card_id:
            pvp_challenges.pop(key, None)
            await callback.answer("У одного из игроков не экипирована главная карта.", show_alert=True)
            return

        pvp_challenges.pop(key, None)
        started = await start_pvp_battle(callback, challenger, accepter)
        if started:
            await callback.answer("Вызов принят, бой начался!")
        else:
            await callback.answer("Не удалось начать бой. Попробуйте снова.", show_alert=True)


@router.callback_query(F.data.startswith("pvp_decline_"))
async def pvp_decline_callback(callback: CallbackQuery):
    challenger_tg = int(callback.data.split("_")[2])
    accepter_tg = callback.from_user.id
    key = (challenger_tg, accepter_tg)
    existed = pvp_challenges.pop(key, None)

    if existed:
        try:
            await callback.bot.send_message(challenger_tg, "❌ Твой PvP-вызов был отклонён.")
        except Exception:
            pass

    await callback.answer("Вызов отклонён.", show_alert=True)
