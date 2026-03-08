import random
from datetime import datetime, timedelta
from aiogram import Router, F
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import async_session, User, UserCard, Curse, Battle
from keyboards.pve import get_pve_menu, get_pve_battle_keyboard, get_pve_result_keyboard
from utils.curse_data import get_curses_for_level, CURSES

router = Router()

# Хранилище активных боев (в памяти, для простоты)
# В продакшене лучше использовать Redis
active_pve_battles = {}

@router.callback_query(F.data == "pve_arena")
async def pve_arena_callback(callback: CallbackQuery):
    """Меню PvE арены"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Проверяем, экипированы ли карты
        if not user.slot_1_card_id:
            await callback.message.edit_text(
                "⚔️ <b>Арена проклятий</b>\n\n"
                "❌ <b>У тебя нет экипированного персонажа!</b>\n\n"
                "Сначала выбери главную карту в профиле.",
                reply_markup=get_pve_menu(),
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        await callback.message.edit_text(
            "👹 <b>Арена проклятий</b>\n\n"
            "Выбери сложность арены:\n\n"
            "🔰 <b>Легкая</b> - для новичков\n"
            "⚔️ <b>Средняя</b> - обычные проклятия\n"
            "👹 <b>Сложная</b> - сильные враги\n"
            "💀 <b>Катастрофа</b> - для мастеров",
            reply_markup=get_pve_menu(),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("pve_"))
async def pve_start_callback(callback: CallbackQuery):
    """Начало PvE боя"""
    if callback.data in ["pve_arena", "pve_attack", "pve_defend", "pve_flee", "pve_next"]:
        if callback.data == "pve_attack":
            await pve_attack_callback(callback)
            return
        elif callback.data == "pve_defend":
            await pve_defend_callback(callback)
            return
        elif callback.data == "pve_flee":
            await pve_flee_callback(callback)
            return
        elif callback.data == "pve_next":
            await pve_next_callback(callback)
            return
        return
    
    difficulty = callback.data.split("_")[1]  # easy, medium, hard, disaster
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Проверяем кулдаун (1 минута между боями)
        if user.last_pve_battle_time:
            time_passed = datetime.utcnow() - user.last_pve_battle_time
            if time_passed < timedelta(minutes=1):
                remaining = 60 - time_passed.seconds
                await callback.answer(
                    f"Подожди {remaining} секунд перед следующим боем!",
                    show_alert=True
                )
                return
        
        # Получаем карты пользователя
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == user.slot_1_card_id)
        )
        main_card = result.scalar_one_or_none()
        
        support_card = None
        if user.slot_2_card_id:
            result = await session.execute(
                select(UserCard)
                .options(selectinload(UserCard.card_template))
                .where(UserCard.id == user.slot_2_card_id)
            )
            support_card = result.scalar_one_or_none()
        
        if not main_card:
            await callback.answer("У тебя нет экипированной карты!", show_alert=True)
            return
        
        # Выбираем проклятие в зависимости от сложности
        if difficulty == "easy":
            available_curses = [c for c in CURSES if c["grade"] <= 3]
        elif difficulty == "medium":
            available_curses = [c for c in CURSES if 3 <= c["grade"] <= 5]
        elif difficulty == "hard":
            available_curses = [c for c in CURSES if 5 <= c["grade"] <= 7]
        else:  # disaster
            available_curses = [c for c in CURSES if c["grade"] >= 8]
        
        # Фильтруем по уровню игрока
        suitable_curses = [c for c in available_curses if c["grade"] <= user.level + 2]
        if not suitable_curses:
            suitable_curses = available_curses[:3]  # Берем самые слабые
        
        curse_data = random.choice(suitable_curses)
        
        # Создаем или получаем проклятие из БД
        result = await session.execute(
            select(Curse).where(Curse.name == curse_data["name"])
        )
        curse = result.scalar_one_or_none()
        
        if not curse:
            curse = Curse(
                name=curse_data["name"],
                description=curse_data["description"],
                grade=curse_data["grade"],
                curse_type=curse_data["curse_type"],
                attack=curse_data["attack"],
                defense=curse_data["defense"],
                speed=curse_data["speed"],
                hp=curse_data["hp"],
                max_hp=curse_data["hp"],
                exp_reward=curse_data["exp_reward"],
                points_reward=curse_data["points_reward"],
                card_drop_chance=curse_data["card_drop_chance"]
            )
            session.add(curse)
            await session.flush()
        
        # Восстанавливаем HP карт
        main_card.heal()
        if support_card:
            support_card.heal()
        
        # Создаем бой в памяти
        battle_id = f"{callback.from_user.id}_{datetime.utcnow().timestamp()}"
        active_pve_battles[callback.from_user.id] = {
            "battle_id": battle_id,
            "user_id": user.id,
            "main_card": main_card,
            "support_card": support_card,
            "curse": curse,
            "turn": 1,
            "log": [],
            "difficulty": difficulty,
            "defending": False
        }
        
        # Определяем, кто первый ходит
        player_speed = main_card.speed + (support_card.speed if support_card else 0)
        curse_speed = curse.speed
        
        battle_text = (
            f"👹 <b>Бой начался!</b>\n\n"
            f"<b>Твоя команда:</b>\n"
            f"👑 {main_card.card_template.name} (❤️ {main_card.hp}/{main_card.max_hp})\n"
        )
        if support_card:
            battle_text += f"🛡️ {support_card.card_template.name} (❤️ {support_card.hp}/{support_card.max_hp})\n"
        
        battle_text += (
            f"\n<b>Противник:</b>\n"
            f"👹 {curse.name} (❤️ {curse.hp}/{curse.max_hp})\n"
            f"📊 Уровень: {curse.grade}\n\n"
        )
        
        if player_speed >= curse_speed:
            battle_text += "⚡ <b>Ты ходишь первым!</b>\n\nВыбери действие:"
        else:
            battle_text += "⚡ <b>Проклятие ходит первым!</b>"
        
        await callback.message.edit_text(
            battle_text,
            reply_markup=get_pve_battle_keyboard(),
            parse_mode="HTML"
        )
        
        # Если проклятие первое - оно атакует
        if player_speed < curse_speed:
            await process_curse_turn(callback, callback.from_user.id)
    
    await callback.answer()

async def process_curse_turn(callback: CallbackQuery, user_id: int):
    """Обработка хода проклятия"""
    battle = active_pve_battles.get(user_id)
    if not battle:
        return
    
    curse = battle["curse"]
    main_card = battle["main_card"]
    support_card = battle["support_card"]
    
    # Проклятие атакует главную карту
    target = main_card
    
    # Рассчитываем урон
    damage = curse.attack
    if battle.get("defending"):
        damage = int(damage * 0.5)  # Уменьшаем урон если защищаемся
    
    actual_damage = target.take_damage(damage)
    battle["log"].append(f"👹 {curse.name} наносит {actual_damage} урона!")
    
    battle_text = (
        f"👹 <b>Бой - Ход {battle['turn']}</b>\n\n"
        f"<b>Твоя команда:</b>\n"
        f"👑 {main_card.card_template.name} (❤️ {main_card.hp}/{main_card.max_hp})\n"
    )
    if support_card:
        battle_text += f"🛡️ {support_card.card_template.name} (❤️ {support_card.hp}/{support_card.max_hp})\n"
    
    battle_text += (
        f"\n<b>Противник:</b>\n"
        f"👹 {curse.name} (❤️ {curse.hp}/{curse.max_hp})\n\n"
        f"⚔️ <b>{curse.name}</b> атакует и наносит <b>{actual_damage}</b> урона!\n\n"
    )
    
    # Проверяем поражение
    if not main_card.is_alive():
        battle_text += "💀 <b>Ты проиграл!</b>"
        await end_pve_battle(callback, user_id, won=False)
        return
    
    battle_text += "Твой ход! Выбери действие:"
    battle["defending"] = False
    
    await callback.message.edit_text(
        battle_text,
        reply_markup=get_pve_battle_keyboard(),
        parse_mode="HTML"
    )

async def pve_attack_callback(callback: CallbackQuery):
    """Атака в PvE"""
    user_id = callback.from_user.id
    battle = active_pve_battles.get(user_id)
    
    if not battle:
        await callback.answer("Бой не найден!", show_alert=True)
        return
    
    main_card = battle["main_card"]
    support_card = battle["support_card"]
    curse = battle["curse"]
    
    # Рассчитываем урон
    damage = main_card.attack
    if support_card:
        damage += support_card.attack // 2  # Поддержка дает половину атаки
    
    actual_damage = curse.take_damage(damage)
    battle["log"].append(f"⚔️ Ты наносишь {actual_damage} урона!")
    
    battle_text = (
        f"👹 <b>Бой - Ход {battle['turn']}</b>\n\n"
        f"<b>Твоя команда:</b>\n"
        f"👑 {main_card.card_template.name} (❤️ {main_card.hp}/{main_card.max_hp})\n"
    )
    if support_card:
        battle_text += f"🛡️ {support_card.card_template.name} (❤️ {support_card.hp}/{support_card.max_hp})\n"
    
    battle_text += (
        f"\n<b>Противник:</b>\n"
        f"👹 {curse.name} (❤️ {curse.hp}/{curse.max_hp})\n\n"
        f"⚔️ <b>Ты атакуешь</b> и наносишь <b>{actual_damage}</b> урона!\n\n"
    )
    
    # Проверяем победу
    if not curse.is_alive():
        battle_text += "🏆 <b>Победа!</b>"
        await end_pve_battle(callback, user_id, won=True)
        return
    
    # Ход проклятия
    battle["turn"] += 1
    
    await callback.message.edit_text(
        battle_text + "Ход противника...",
        parse_mode="HTML"
    )
    
    # Имитируем задержку и ход проклятия
    import asyncio
    await asyncio.sleep(1)
    await process_curse_turn(callback, user_id)

async def pve_defend_callback(callback: CallbackQuery):
    """Защита в PvE"""
    user_id = callback.from_user.id
    battle = active_pve_battles.get(user_id)
    
    if not battle:
        await callback.answer("Бой не найден!", show_alert=True)
        return
    
    battle["defending"] = True
    battle["log"].append("🛡️ Ты принимаешь защитную стойку!")
    
    main_card = battle["main_card"]
    support_card = battle["support_card"]
    curse = battle["curse"]
    
    battle_text = (
        f"👹 <b>Бой - Ход {battle['turn']}</b>\n\n"
        f"<b>Твоя команда:</b>\n"
        f"👑 {main_card.card_template.name} (❤️ {main_card.hp}/{main_card.max_hp})\n"
    )
    if support_card:
        battle_text += f"🛡️ {support_card.card_template.name} (❤️ {support_card.hp}/{support_card.max_hp})\n"
    
    battle_text += (
        f"\n<b>Противник:</b>\n"
        f"👹 {curse.name} (❤️ {curse.hp}/{curse.max_hp})\n\n"
        f"🛡️ <b>Ты принимаешь защитную стойку!</b>\n"
        f"Получаемый урон уменьшен на 50%\n\n"
        f"Ход противника..."
    )
    
    await callback.message.edit_text(battle_text, parse_mode="HTML")
    
    # Ход проклятия
    battle["turn"] += 1
    import asyncio
    await asyncio.sleep(1)
    await process_curse_turn(callback, user_id)

async def pve_flee_callback(callback: CallbackQuery):
    """Побег из боя"""
    user_id = callback.from_user.id
    
    if user_id in active_pve_battles:
        del active_pve_battles[user_id]
    
    await callback.message.edit_text(
        "🏃 <b>Ты сбежал с поля боя!</b>\n\n"
        "Проклятие осталось живо...",
        reply_markup=get_pve_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

async def end_pve_battle(callback: CallbackQuery, user_id: int, won: bool):
    """Завершение PvE боя"""
    battle = active_pve_battles.get(user_id)
    if not battle:
        return
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.id == battle["user_id"])
        )
        user = result.scalar_one_or_none()
        
        if user:
            user.last_pve_battle_time = datetime.utcnow()
            user.total_battles += 1
            
            if won:
                user.pve_wins += 1
                curse = battle["curse"]
                
                # Награды
                exp_gained = curse.exp_reward
                points_gained = curse.points_reward
                
                # Бонус за сложность
                if battle["difficulty"] == "medium":
                    exp_gained = int(exp_gained * 1.2)
                    points_gained = int(points_gained * 1.2)
                elif battle["difficulty"] == "hard":
                    exp_gained = int(exp_gained * 1.5)
                    points_gained = int(points_gained * 1.5)
                elif battle["difficulty"] == "disaster":
                    exp_gained = int(exp_gained * 2)
                    points_gained = int(points_gained * 2)
                
                # Добавляем опыт
                leveled_up, actual_exp = user.add_experience(exp_gained)
                user.points += points_gained
                
                # Шанс выпадения карты
                card_dropped = random.random() * 100 < curse.card_drop_chance
                
                await session.commit()
                
                result_text = (
                    f"🏆 <b>Победа!</b>\n\n"
                    f"⭐ Опыт: +{actual_exp}\n"
                    f"💎 Очки: +{points_gained}\n"
                )
                
                if leveled_up:
                    result_text += f"🎉 <b>Новый уровень! Теперь ты {user.level} уровня!</b>\n"
                
                if card_dropped:
                    result_text += "🎴 <b>Выпала новая карта!</b>\n"
                    # Здесь можно добавить логику выпадения карты
                
                result_text += f"\n💪 Твоя сила растет!"
                
            else:
                user.pve_losses += 1
                await session.commit()
                
                result_text = (
                    f"💀 <b>Поражение...</b>\n\n"
                    f"Не сдавайся! Прокачай карты и попробуй снова."
                )
            
            # Сохраняем бой в историю
            battle_record = Battle(
                battle_type="pve",
                player1_id=user.id,
                curse_id=battle["curse"].id,
                curse_name=battle["curse"].name,
                winner_id=user.id if won else None,
                battle_log="\n".join(battle["log"]),
                exp_gained=exp_gained if won else 0,
                points_gained=points_gained if won else 0
            )
            session.add(battle_record)
            await session.commit()
            
            await callback.message.edit_text(
                result_text,
                reply_markup=get_pve_result_keyboard(won),
                parse_mode="HTML"
            )
    
    # Удаляем бой из памяти
    if user_id in active_pve_battles:
        del active_pve_battles[user_id]

async def pve_next_callback(callback: CallbackQuery):
    """Следующий бой"""
    # Просто перезапускаем бой с той же сложностью
    # Нужно сохранить difficulty где-то или передавать
    await pve_arena_callback(callback)
