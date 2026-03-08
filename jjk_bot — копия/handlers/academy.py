from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import random

from models import async_session, User, AcademyLesson, UserAcademyVisit, Technique, UserTechnique
from utils.technique_data import ALL_TECHNIQUES

router = Router()

@router.message(Command("academy"))
async def cmd_academy(message: Message):
    """Команда /academy"""
    await message.answer(
        "🏫 <b>Техникум Магии</b>\n\n"
        "Нажми кнопку, чтобы открыть техникум.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏫 Открыть техникум", callback_data="academy")]
        ]),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "academy")
async def academy_menu_callback(callback: CallbackQuery):
    """Меню техникума"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем или создаем запись о посещениях
        result = await session.execute(
            select(UserAcademyVisit).where(UserAcademyVisit.user_id == user.id)
        )
        visit = result.scalar_one_or_none()
        
        if not visit:
            visit = UserAcademyVisit(user_id=user.id)
            session.add(visit)
            await session.commit()
        
        can_visit = visit.can_visit()
        remaining_hours = visit.get_remaining_cooldown()
        
        menu_text = (
            f"🏫 <b>Техникум Магии</b>\n\n"
            f"Здесь ты можешь обучаться новым техникам и способностям.\n\n"
            f"📊 Посещений: <b>{visit.total_visits}</b>\n"
            f"💰 Твои монеты: <b>{user.coins}</b>\n\n"
        )
        
        if can_visit:
            menu_text += "✅ <b>Техникум открыт!</b>\n"
        else:
            hours = int(remaining_hours)
            minutes = int((remaining_hours - hours) * 60)
            menu_text += f"⏳ Следующее посещение через: {hours}ч {minutes}м\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[])
        
        if can_visit:
            keyboard.inline_keyboard.append([
                InlineKeyboardButton(text="📚 Начать Обучение", callback_data="academy_learn")
            ])
        
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ])
        
        await callback.message.edit_text(menu_text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "academy_learn")
async def academy_learn_callback(callback: CallbackQuery):
    """Обучение в техникуме"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(UserAcademyVisit).where(UserAcademyVisit.user_id == user.id)
        )
        visit = result.scalar_one_or_none()
        
        if not visit or not visit.can_visit():
            await callback.answer("Техникум закрыт! Приходи позже.", show_alert=True)
            return
        
        # Стоимость обучения
        cost = 500 + (visit.total_visits * 100)
        
        if user.coins < cost:
            await callback.answer(f"Недостаточно монет! Нужно: {cost}", show_alert=True)
            return
        
        # Списываем монеты
        user.coins -= cost
        
        # Обновляем посещение
        visit.total_visits += 1
        visit.last_visit = datetime.utcnow()
        
        # Определяем результат обучения
        outcomes = [
            ("technique", 30),  # 30% - новая техника
            ("stat_boost", 40),  # 40% - улучшение характеристик
            ("nothing", 30)  # 30% - ничего
        ]
        
        outcome = random.choices([o[0] for o in outcomes], weights=[o[1] for o in outcomes])[0]
        
        result_text = (
            f"🏫 <b>Обучение в Техникуме</b>\n\n"
            f"💰 Потрачено: {cost} монет\n\n"
        )
        
        if outcome == "technique":
            # Выдаем случайную технику
            available_techniques = [t for t in ALL_TECHNIQUES if t["rarity"] in ["common", "rare"]]
            technique_data = random.choice(available_techniques)
            
            # Проверяем, есть ли уже
            result = await session.execute(
                select(Technique).where(Technique.name == technique_data["name"])
            )
            tech_template = result.scalar_one_or_none()
            
            if not tech_template:
                tech_template = Technique(
                    name=technique_data["name"],
                    description=technique_data["description"],
                    technique_type=technique_data["technique_type"],
                    ce_cost=technique_data.get("ce_cost", 0),
                    effect_type=technique_data.get("effect_type"),
                    effect_value=technique_data.get("effect_value", 0),
                    trigger_chance=technique_data.get("trigger_chance", 0),
                    duration=technique_data.get("duration", 0),
                    icon=technique_data["icon"],
                    rarity=technique_data["rarity"]
                )
                session.add(tech_template)
                await session.flush()
            
            # Проверяем, есть ли у пользователя
            result = await session.execute(
                select(UserTechnique).where(
                    UserTechnique.user_id == user.id,
                    UserTechnique.technique_id == tech_template.id
                )
            )
            existing = result.scalar_one_or_none()
            
            if existing:
                result_text += (
                    f"📚 Ты изучил технику, но уже знаешь её!\n"
                    f"✨ <b>{technique_data['icon']} {technique_data['name']}</b>\n"
                    f"Вместо этого ты получил бонус:\n"
                    f"⭐ 100 опыта\n"
                )
                user.add_experience(100)
            else:
                user_tech = UserTechnique(
                    user_id=user.id,
                    technique_id=tech_template.id,
                    level=1,
                    is_equipped=False
                )
                session.add(user_tech)
                
                result_text += (
                    f"🎉 <b>Новая техника изучена!</b>\n\n"
                    f"{technique_data['icon']} <b>{technique_data['name']}</b>\n"
                    f"<i>{technique_data['description']}</i>\n\n"
                    f"Тип: {technique_data['technique_type']}\n"
                    f"Редкость: {technique_data['rarity']}\n"
                )
                
                if technique_data.get("ce_cost"):
                    result_text += f"💧 Стоимость CE: {technique_data['ce_cost']}\n"
        
        elif outcome == "stat_boost":
            # Улучшаем характеристики
            stats = ["attack", "defense", "speed", "hp"]
            stat = random.choice(stats)
            boost = random.randint(5, 15)
            
            # Применяем к главной карте
            result = await session.execute(
                select(UserCard)
                .options(selectinload(UserCard.card_template))
                .where(UserCard.user_id == user.id, UserCard.slot_number == 1)
            )
            main_card = result.scalar_one_or_none()
            
            if main_card:
                if stat == "attack":
                    main_card.attack += boost
                elif stat == "defense":
                    main_card.defense += boost
                elif stat == "speed":
                    main_card.speed += boost
                elif stat == "hp":
                    main_card.max_hp += boost
                    main_card.hp += boost
                
                stat_names = {
                    "attack": "⚔️ Атака",
                    "defense": "🛡️ Защита",
                    "speed": "💨 Скорость",
                    "hp": "❤️ HP"
                }
                
                result_text += (
                    f"💪 <b>Характеристики улучшены!</b>\n\n"
                    f"{stat_names[stat]}: +{boost}\n"
                    f"(применено к {main_card.card_template.name})\n"
                )
            else:
                # Если нет карты - даем опыт
                result_text += (
                    f"📚 Ты усвоил знания!\n"
                    f"⭐ Получено 150 опыта\n"
                )
                user.add_experience(150)
        
        else:  # nothing
            result_text += (
                f"📚 Ты учился, но ничего не понял...\n"
                f"В следующий раз повезет больше!\n\n"
                f"Но ты получил немного опыта:\n"
                f"⭐ 50 опыта\n"
            )
            user.add_experience(50)
        
        await session.commit()
        
        await callback.message.edit_text(
            result_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🏫 Вернуться в Техникум", callback_data="academy")],
                [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
            ]),
            parse_mode="HTML"
        )
    await callback.answer()


from datetime import datetime
