import random
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from models import async_session, User, UserCard, Battle
from keyboards.pvp import get_pvp_menu, get_pvp_search_keyboard, get_pvp_battle_keyboard, get_pvp_result_keyboard

router = Router()

# Хранилище активных PvP боев
active_pvp_battles = {}
pvp_challenges = {}  # Вызовы на бой


def _find_battle_by_user_tg(telegram_id: int):
    for battle in active_pvp_battles.values():
        if battle["player1_tg"] == telegram_id or battle["player2_tg"] == telegram_id:
            return battle
    return None


def _battle_view_text(battle: dict, viewer_tg: int) -> str:
    p1_main = battle["p1_main"]
    p1_support = battle["p1_support"]
    p2_main = battle["p2_main"]
    p2_support = battle["p2_support"]

    viewer_is_p1 = viewer_tg == battle["player1_tg"]
    you_label = "Игрок 1" if viewer_is_p1 else "Игрок 2"
    enemy_label = "Игрок 2" if viewer_is_p1 else "Игрок 1"
    your_main = p1_main if viewer_is_p1 else p2_main
    your_support = p1_support if viewer_is_p1 else p2_support
    enemy_main = p2_main if viewer_is_p1 else p1_main
    enemy_support = p2_support if viewer_is_p1 else p1_support

    text = (
        f"⚔️ <b>PvP Бой - Ход {battle['turn']}</b>\n\n"
        f"<b>Ты ({you_label}):</b>\n"
        f"👑 {your_main.card_template.name} (❤️ {your_main.hp}/{your_main.max_hp})\n"
    )
    if your_support:
        text += f"🛡️ {your_support.card_template.name} (❤️ {your_support.hp}/{your_support.max_hp})\n"

    text += (
        f"\n<b>Противник ({enemy_label}):</b>\n"
        f"👑 {enemy_main.card_template.name} (❤️ {enemy_main.hp}/{enemy_main.max_hp})\n"
    )
    if enemy_support:
        text += f"🛡️ {enemy_support.card_template.name} (❤️ {enemy_support.hp}/{enemy_support.max_hp})\n"

    is_your_turn = (viewer_is_p1 and battle["current_player"] == 1) or (not viewer_is_p1 and battle["current_player"] == 2)
    text += "\n⚡ <b>Твой ход!</b>" if is_your_turn else "\n⏳ <b>Ход противника...</b>"
    return text


async def _edit_or_send_battle_message(callback: CallbackQuery, telegram_id: int, text: str, is_your_turn: bool):
    keyboard = get_pvp_battle_keyboard(is_your_turn=is_your_turn)
    battle = _find_battle_by_user_tg(telegram_id)

    if not battle:
        return None

    existing_id = battle["messages"].get(telegram_id)

    # Если это текущее callback-сообщение пользователя, стараемся редактировать его
    if callback.from_user.id == telegram_id and callback.message:
        try:
            edited = await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
            battle["messages"][telegram_id] = edited.message_id
            return edited
        except Exception:
            pass

    # Иначе пробуем редактировать сохраненное сообщение
    if existing_id:
        try:
            edited = await callback.bot.edit_message_text(
                chat_id=telegram_id,
                message_id=existing_id,
                text=text,
                reply_markup=keyboard,
                parse_mode="HTML"
            )
            if hasattr(edited, "message_id"):
                battle["messages"][telegram_id] = edited.message_id
            return edited
        except Exception:
            pass

    # Фоллбек: отправляем новое сообщение
    try:
        sent = await callback.bot.send_message(
            telegram_id,
            text,
            reply_markup=keyboard,
            parse_mode="HTML"
        )
        battle["messages"][telegram_id] = sent.message_id
        return sent
    except Exception:
        return None


async def _update_battle_messages(callback: CallbackQuery, battle: dict):
    p1_tg = battle["player1_tg"]
    p2_tg = battle["player2_tg"]

    p1_text = _battle_view_text(battle, p1_tg)
    p2_text = _battle_view_text(battle, p2_tg)

    p1_turn = battle["current_player"] == 1
    p2_turn = battle["current_player"] == 2

    await _edit_or_send_battle_message(callback, p1_tg, p1_text, p1_turn)
    await _edit_or_send_battle_message(callback, p2_tg, p2_text, p2_turn)

@router.message(Command("pvp"))
async def cmd_pvp(message: Message):
    """Команда /pvp"""
    await message.answer(
        "⚔️ <b>PvP Арена</b>\n\n"
        "Выбери действие:",
        reply_markup=get_pvp_menu(),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "pvp_menu")
async def pvp_menu_callback(callback: CallbackQuery):
    """Меню PvP"""
    await callback.message.edit_text(
        "⚔️ <b>PvP Арена</b>\n\n"
        "Сражайся с другими игроками и докажи свое превосходство!\n\n"
        "🏆 Побеждай, получай опыт и поднимайся в топах!",
        reply_markup=get_pvp_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

@router.callback_query(F.data == "pvp_find")
async def pvp_find_callback(callback: CallbackQuery):
    """Поиск соперника"""
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
        
        # Проверяем кулдаун (2 минуты между PvP боями)
        if user.last_battle_time:
            time_passed = datetime.utcnow() - user.last_battle_time
            if time_passed < timedelta(minutes=2):
                remaining = 120 - time_passed.seconds
                await callback.answer(
                    f"Подожди {remaining} секунд перед следующим PvP боем!",
                    show_alert=True
                )
                return
        
        # Проверяем колоду
        if not user.slot_1_card_id:
            await callback.answer("У тебя нет экипированной карты!", show_alert=True)
            return
        
        # Ищем случайного соперника примерно того же уровня
        result = await session.execute(
            select(User)
            .where(
                User.telegram_id != callback.from_user.id,
                User.level >= user.level - 5,
                User.level <= user.level + 5,
                User.slot_1_card_id.isnot(None)
            )
            .order_by(func.random())
            .limit(1)
        )
        opponent = result.scalar_one_or_none()
        
        if not opponent:
            await callback.message.edit_text(
                "🔍 <b>Соперник не найден</b>\n\n"
                "Пока нет подходящих соперников твоего уровня.\n"
                "Попробуй позже или вызови конкретного игрока!",
                reply_markup=get_pvp_search_keyboard(),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        if _find_battle_by_user_tg(opponent.telegram_id):
            await callback.answer("Соперник уже в бою, попробуй еще раз.", show_alert=True)
            return
        
        # Начинаем бой
        await start_pvp_battle(callback, user, opponent)
    
    await callback.answer()

async def start_pvp_battle(callback: CallbackQuery, player1: User, player2: User, is_rematch: bool = False):
    """Начало PvP боя"""
    async with async_session() as session:
        # Получаем карты обоих игроков
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == player1.slot_1_card_id)
        )
        p1_main = result.scalar_one_or_none()
        
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == player1.slot_2_card_id)
        )
        p1_support = result.scalar_one_or_none()
        
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == player2.slot_1_card_id)
        )
        p2_main = result.scalar_one_or_none()
        
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == player2.slot_2_card_id)
        )
        p2_support = result.scalar_one_or_none()
        
        if not p1_main or not p2_main:
            await callback.answer("У одного из игроков нет колоды!", show_alert=True)
            return
        
        # Восстанавливаем HP
        p1_main.heal()
        p2_main.heal()
        if p1_support:
            p1_support.heal()
        if p2_support:
            p2_support.heal()
        
        # Создаем бой
        battle_id = f"pvp_{player1.id}_{player2.id}_{datetime.utcnow().timestamp()}"
        
        active_pvp_battles[player1.telegram_id] = {
            "battle_id": battle_id,
            "player1_id": player1.id,
            "player1_tg": player1.telegram_id,
            "player2_id": player2.id,
            "player2_tg": player2.telegram_id,
            "p1_main": p1_main,
            "p1_support": p1_support,
            "p2_main": p2_main,
            "p2_support": p2_support,
            "turn": 1,
            "current_player": 1,  # 1 или 2
            "log": [],
            "defending": {1: False, 2: False},
            "messages": {}
        }
        
        # Определяем, кто первый ходит
        p1_speed = p1_main.speed + (p1_support.speed if p1_support else 0)
        p2_speed = p2_main.speed + (p2_support.speed if p2_support else 0)
        
        if p1_speed >= p2_speed:
            active_pvp_battles[player1.telegram_id]["current_player"] = 1
        else:
            active_pvp_battles[player1.telegram_id]["current_player"] = 2
        
        battle = active_pvp_battles[player1.telegram_id]
        await _update_battle_messages(callback, battle)

@router.callback_query(F.data.startswith("pvp_attack"))
async def pvp_attack_callback(callback: CallbackQuery):
    """Атака в PvP"""
    user_id = callback.from_user.id
    battle = _find_battle_by_user_tg(user_id)
    
    if not battle:
        await callback.answer("Бой не найден!", show_alert=True)
        return
    
    # Определяем, кто атакует
    is_player1 = battle["player1_tg"] == user_id
    current = battle["current_player"]
    
    if (is_player1 and current != 1) or (not is_player1 and current != 2):
        await callback.answer("Сейчас не твой ход!", show_alert=True)
        return
    
    # Получаем карты
    if is_player1:
        attacker_main = battle["p1_main"]
        attacker_support = battle["p1_support"]
        defender_main = battle["p2_main"]
        defender_support = battle["p2_support"]
        defender_num = 2
    else:
        attacker_main = battle["p2_main"]
        attacker_support = battle["p2_support"]
        defender_main = battle["p1_main"]
        defender_support = battle["p1_support"]
        defender_num = 1
    
    # Рассчитываем урон
    damage = attacker_main.attack
    if attacker_support:
        damage += attacker_support.attack // 2
    
    # Учитываем защиту
    if battle["defending"][defender_num]:
        damage = int(damage * 0.5)
    
    actual_damage = defender_main.take_damage(damage)
    battle["log"].append(f"⚔️ Атака наносит {actual_damage} урона!")
    
    # Сбрасываем защиту
    battle["defending"][defender_num] = False
    
    # Проверяем победу
    if not defender_main.is_alive():
        await end_pvp_battle(callback, battle, winner_is_player1=is_player1)
        return
    
    # Меняем ход
    battle["current_player"] = 2 if current == 1 else 1
    battle["turn"] += 1
    
    # Обновляем сообщение
    await _update_battle_messages(callback, battle)
    await callback.answer()

@router.callback_query(F.data.startswith("pvp_defend"))
async def pvp_defend_callback(callback: CallbackQuery):
    """Защита в PvP"""
    user_id = callback.from_user.id
    battle = _find_battle_by_user_tg(user_id)
    
    if not battle:
        await callback.answer("Бой не найден!", show_alert=True)
        return
    
    is_player1 = battle["player1_tg"] == user_id
    current = battle["current_player"]
    
    if (is_player1 and current != 1) or (not is_player1 and current != 2):
        await callback.answer("Сейчас не твой ход!", show_alert=True)
        return
    
    player_num = 1 if is_player1 else 2
    battle["defending"][player_num] = True
    battle["log"].append("🛡️ Защитная стойка!")
    
    # Меняем ход
    battle["current_player"] = 2 if current == 1 else 1
    battle["turn"] += 1
    
    await _update_battle_messages(callback, battle)
    await callback.answer("Защита активирована!")

async def end_pvp_battle(callback: CallbackQuery, battle: dict, winner_is_player1: bool):
    """Завершение PvP боя"""
    async with async_session() as session:
        # Получаем игроков
        result = await session.execute(
            select(User).where(User.id == battle["player1_id"])
        )
        player1 = result.scalar_one()
        
        result = await session.execute(
            select(User).where(User.id == battle["player2_id"])
        )
        player2 = result.scalar_one()
        
        winner = player1 if winner_is_player1 else player2
        loser = player2 if winner_is_player1 else player1
        
        # Обновляем статистику
        winner.pvp_wins += 1
        winner.total_battles += 1
        winner.last_battle_time = datetime.utcnow()
        
        loser.pvp_losses += 1
        loser.total_battles += 1
        loser.last_battle_time = datetime.utcnow()
        
        # Награды победителю
        exp_gained = 50
        points_gained = 5
        
        # Бонус за разницу уровней
        level_diff = loser.level - winner.level
        if level_diff > 0:
            exp_gained += level_diff * 10
            points_gained += level_diff
        
        leveled_up, actual_exp = winner.add_experience(exp_gained)
        winner.points += points_gained
        
        await session.commit()
        
        # Сохраняем бой
        battle_record = Battle(
            battle_type="pvp",
            player1_id=player1.id,
            player2_id=player2.id,
            winner_id=winner.id,
            battle_log="\n".join(battle["log"]),
            exp_gained=actual_exp,
            points_gained=points_gained
        )
        session.add(battle_record)
        await session.commit()
        
        # Сообщения результата для обоих игроков
        winner_text = (
            f"🏆 <b>Победа!</b>\n\n"
            f"Ты победил {loser.first_name or 'противника'}!\n\n"
            f"⭐ Опыт: +{actual_exp}\n"
            f"💎 Очки: +{points_gained}\n"
        )
        if leveled_up:
            winner_text += f"🎉 <b>Новый уровень! Теперь ты {winner.level} уровня!</b>\n"

        loser_text = (
            f"💀 <b>Поражение...</b>\n\n"
            f"{winner.first_name or 'Противник'} оказался сильнее.\n\n"
            f"Не сдавайся, прокачай карты и попробуй снова!"
        )

        # Победитель
        try:
            await callback.bot.send_message(
                winner.telegram_id,
                winner_text,
                reply_markup=get_pvp_result_keyboard(True),
                parse_mode="HTML"
            )
        except Exception:
            pass

        # Проигравший
        try:
            await callback.bot.send_message(
                loser.telegram_id,
                loser_text,
                reply_markup=get_pvp_result_keyboard(False),
                parse_mode="HTML"
            )
        except Exception:
            pass
    
    # Удаляем бой
    for uid, b in list(active_pvp_battles.items()):
        if b["battle_id"] == battle["battle_id"]:
            del active_pvp_battles[uid]

@router.callback_query(F.data == "pvp_history")
async def pvp_history_callback(callback: CallbackQuery):
    """История PvP боев"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(Battle)
            .options(
                selectinload(Battle.player1),
                selectinload(Battle.player2)
            )
            .where(
                Battle.battle_type == "pvp",
                (Battle.player1_id == user.id) | (Battle.player2_id == user.id)
            )
            .order_by(Battle.created_at.desc())
            .limit(10)
        )
        battles = result.scalars().all()
        
        if not battles:
            await callback.message.edit_text(
                "📜 <b>История PvP</b>\n\n"
                "У тебя пока нет PvP боев.",
                reply_markup=get_pvp_menu(),
                parse_mode="HTML"
            )
            return
        
        history_text = "📜 <b>Последние PvP бои:</b>\n\n"
        
        for i, battle in enumerate(battles, 1):
            opponent_name = battle.get_opponent_name(user.id)
            is_winner = battle.winner_id == user.id
            result_emoji = "🏆" if is_winner else "💀"
            
            history_text += f"{i}. {result_emoji} vs {opponent_name}\n"
        
        from keyboards.main_menu import get_back_button
        await callback.message.edit_text(
            history_text,
            reply_markup=get_back_button("pvp_menu"),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "pvp_challenge")
async def pvp_challenge_callback(callback: CallbackQuery):
    """Подсказка по вызову игрока"""
    from keyboards.main_menu import get_back_button

    await callback.message.edit_text(
        "🎯 <b>Вызов игрока</b>\n\n"
        "Функция прямого вызова в разработке.\n"
        "Пока используй поиск соперника или бои через раздел друзей.",
        reply_markup=get_back_button("pvp_menu"),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "pvp_special")
async def pvp_special_callback(callback: CallbackQuery):
    """Специальная атака временно недоступна"""
    await callback.answer("Специальные атаки пока не реализованы.", show_alert=True)


@router.callback_query(F.data == "pvp_rematch")
async def pvp_rematch_callback(callback: CallbackQuery):
    """Реванш через стандартный поиск"""
    await pvp_find_callback(callback)


@router.callback_query(F.data.startswith("pvp_accept_"))
async def pvp_accept_callback(callback: CallbackQuery):
    """Принять прямой вызов"""
    challenger_tg = int(callback.data.split("_")[2])
    accepter_tg = callback.from_user.id
    key = (challenger_tg, accepter_tg)

    created_at = pvp_challenges.get(key)
    if not created_at:
        await callback.answer("Вызов не найден или уже неактуален.", show_alert=True)
        return

    # Просроченный вызов
    if datetime.utcnow() - created_at > timedelta(minutes=10):
        pvp_challenges.pop(key, None)
        await callback.answer("Вызов истек. Отправьте новый.", show_alert=True)
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
        await start_pvp_battle(callback, challenger, accepter)
        await callback.answer("Вызов принят, бой начался!")


@router.callback_query(F.data.startswith("pvp_decline_"))
async def pvp_decline_callback(callback: CallbackQuery):
    """Отклонить прямой вызов"""
    challenger_tg = int(callback.data.split("_")[2])
    accepter_tg = callback.from_user.id
    key = (challenger_tg, accepter_tg)
    existed = pvp_challenges.pop(key, None)

    if existed:
        try:
            await callback.bot.send_message(challenger_tg, "❌ Твой вызов на PvP был отклонен.")
        except Exception:
            pass

    await callback.answer("Вызов отклонен.", show_alert=True)
