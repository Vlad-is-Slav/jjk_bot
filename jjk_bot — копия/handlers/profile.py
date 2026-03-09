import html
from pathlib import Path

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from models import async_session, User, UserCard, UserProfile, UserQuote
from keyboards import get_profile_menu, get_deck_keyboard, get_difficulty_menu
from utils.card_rewards import is_character_template, is_support_template
from utils.quote_rewards import ensure_quotes_for_owned_cards

router = Router()
PROFILE_PAGE_SIZE = 6
QUOTE_PAGE_SIZE = 5
CARD_IMAGE_EXTENSIONS = ("jpg", "jpeg", "png", "webp")
CARD_ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "cards"


async def _get_or_create_user_profile(session, user_id: int) -> UserProfile:
    result = await session.execute(
        select(UserProfile).where(UserProfile.user_id == user_id)
    )
    profile_settings = result.scalar_one_or_none()
    if profile_settings:
        return profile_settings

    profile_settings = UserProfile(user_id=user_id)
    session.add(profile_settings)
    await session.flush()
    return profile_settings


async def _load_profile_state(session, user: User):
    profile_settings = await _get_or_create_user_profile(session, user.id)
    avatar_card = None
    changed = False

    if profile_settings.avatar_card_id:
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(
                UserCard.id == profile_settings.avatar_card_id,
                UserCard.user_id == user.id,
            )
        )
        avatar_card = result.scalar_one_or_none()

        if (
            not avatar_card
            or not avatar_card.card_template
            or not is_character_template(avatar_card.card_template)
        ):
            profile_settings.avatar_card_id = None
            avatar_card = None
            changed = True

    favorite_quote = (profile_settings.favorite_quote or "").strip() or None
    return profile_settings, avatar_card, favorite_quote, changed


def _quote_preview(quote: str, max_len: int = 80) -> str:
    if len(quote) <= max_len:
        return quote
    return quote[: max_len - 1].rstrip() + "…"


def _card_image_variants(card_name: str) -> list[str]:
    base = (card_name or "").strip()
    if not base:
        return []

    normalized_space = " ".join(base.split())
    variants = {
        normalized_space,
        normalized_space.replace(" ", "_"),
        normalized_space.replace(" ", "-"),
        normalized_space.replace("ё", "е").replace("Ё", "Е"),
    }
    variants.update({
        name.replace(" ", "_")
        for name in list(variants)
    })
    variants.update({
        name.replace(" ", "-")
        for name in list(variants)
    })
    return [name for name in variants if name]


def _resolve_avatar_image_path(avatar_card: UserCard | None) -> Path | None:
    if not avatar_card or not avatar_card.card_template:
        return None
    if not CARD_ASSETS_DIR.exists():
        return None

    for base_name in _card_image_variants(avatar_card.card_template.name):
        for ext in CARD_IMAGE_EXTENSIONS:
            candidate = CARD_ASSETS_DIR / f"{base_name}.{ext}"
            if candidate.exists():
                return candidate
    return None


def _profile_customization_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🖼 Выбрать аватар", callback_data="profile_avatar_menu_0"),
                InlineKeyboardButton(text="💬 Выбрать цитату", callback_data="profile_quote_menu_0"),
            ],
            [
                InlineKeyboardButton(text="♻️ Сбросить аватар", callback_data="profile_avatar_clear"),
                InlineKeyboardButton(text="♻️ Сбросить цитату", callback_data="profile_quote_clear"),
            ],
            [InlineKeyboardButton(text="🔙 В профиль", callback_data="profile")],
        ]
    )


async def _render_profile_customization(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        granted_quotes = await ensure_quotes_for_owned_cards(session, user.id)
        profile_settings, avatar_card, favorite_quote, changed = await _load_profile_state(session, user)
        if granted_quotes or changed:
            await session.commit()

        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.user_id == user.id)
        )
        all_cards = result.scalars().all()
        character_count = len([card for card in all_cards if card.card_template and is_character_template(card.card_template)])

        result = await session.execute(
            select(UserQuote).where(UserQuote.user_id == user.id)
        )
        unlocked_quotes = result.scalars().all()

        avatar_name = (
            avatar_card.card_template.name
            if avatar_card and avatar_card.card_template
            else "Стандартный"
        )
        quote_text = f"«{html.escape(_quote_preview(favorite_quote))}»" if favorite_quote else "не выбрана"
        avatar_image_path = _resolve_avatar_image_path(avatar_card)
        avatar_file_status = "найден" if avatar_image_path else "не найден"

        text = (
            "🖼️ <b>Оформление профиля</b>\n\n"
            "Здесь можно менять только безопасные элементы:\n"
            "• аватар только из твоих карт-персонажей\n"
            "• цитату только из открытых цитат\n\n"
            f"🖼 Текущий аватар: <b>{html.escape(avatar_name)}</b>\n"
            f"💬 Текущая цитата: {quote_text}\n\n"
            f"🎴 Доступно карт-персонажей: <b>{character_count}</b>\n"
            f"📜 Открыто цитат: <b>{len(unlocked_quotes)}</b>\n"
            f"🗂 Файл аватара: <b>{avatar_file_status}</b>"
        )

        await callback.message.edit_text(
            text,
            reply_markup=_profile_customization_keyboard(),
            parse_mode="HTML",
        )


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Команда /profile"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await message.answer("Сначала используй /start")
            return

        _, avatar_card, favorite_quote, changed = await _load_profile_state(session, user)
        if changed:
            await session.commit()

        avatar_name = (
            avatar_card.card_template.name
            if avatar_card and avatar_card.card_template
            else "Стандартный"
        )
        quote_line = f"«{html.escape(_quote_preview(favorite_quote))}»" if favorite_quote else "не выбрана"
        avatar_image_path = _resolve_avatar_image_path(avatar_card)
        avatar_file_line = "есть" if avatar_image_path else "не найден"

        profile_text = (
            f"👤 <b>Профиль: {user.first_name or 'Маг'}</b>\n\n"
            f"⭐ Уровень: {user.level}\n"
            f"📈 Опыт: {user.experience}/{user.experience_to_next}\n"
            f"💎 Очки: {user.points}\n"
            f"🪙 Монеты: {user.coins}\n\n"
            f"🖼 Аватар: {html.escape(avatar_name)}\n"
            f"💬 Цитата: {quote_line}\n"
            f"🗂 Файл аватара: {avatar_file_line}"
        )

        await message.answer(profile_text, reply_markup=get_profile_menu(), parse_mode="HTML")

@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery):
    """Профиль игрока"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем экипированные карты
        main_card = None
        support_card = None
        
        if user.slot_1_card_id:
            result = await session.execute(
                select(UserCard)
                .options(selectinload(UserCard.card_template))
                .where(UserCard.id == user.slot_1_card_id)
            )
            main_card = result.scalar_one_or_none()
        
        if user.slot_2_card_id:
            result = await session.execute(
                select(UserCard)
                .options(selectinload(UserCard.card_template))
                .where(UserCard.id == user.slot_2_card_id)
            )
            support_card = result.scalar_one_or_none()
        
        # Рассчитываем общую силу
        total_power = 0
        if main_card:
            total_power += main_card.get_total_power()
        if support_card:
            total_power += support_card.get_total_power()
        
        profile_text = (
            f"👤 <b>Профиль: {user.first_name or 'Маг'}</b>\n"
            f"@{user.username or 'Нет username'}\n\n"
            f"📊 <b>Статистика:</b>\n"
            f"⭐ Уровень: {user.level}\n"
            f"📈 Опыт: {user.experience}/{user.experience_to_next}\n"
            f"💎 Очки: {user.points}\n"
            f"💪 Общая сила: {total_power}\n\n"
            f"⚔️ <b>Боевая статистика:</b>\n"
            f"🏆 PvP побед: {user.pvp_wins}\n"
            f"💀 PvP поражений: {user.pvp_losses}\n"
            f"📊 Winrate: {user.get_win_rate()}%\n"
            f"👹 PvE побед: {user.pve_wins}\n"
            f"📊 Всего боев: {user.total_battles}\n\n"
            f"🎴 <b>Колода:</b>\n"
        )
        
        if main_card and main_card.card_template:
            profile_text += f"👑 {main_card.card_template.name} (Lv.{main_card.level})\n"
        else:
            profile_text += "👑 Не выбрано\n"
        
        if support_card and support_card.card_template:
            profile_text += f"🛡️ {support_card.card_template.name} (Lv.{support_card.level})\n"
        else:
            profile_text += "🛡️ Не выбрано\n"

        _, avatar_card, favorite_quote, changed = await _load_profile_state(session, user)
        if changed:
            await session.commit()

        avatar_name = (
            avatar_card.card_template.name
            if avatar_card and avatar_card.card_template
            else "Стандартный"
        )
        quote_line = f"«{html.escape(_quote_preview(favorite_quote))}»" if favorite_quote else "не выбрана"
        avatar_image_path = _resolve_avatar_image_path(avatar_card)
        avatar_file_line = "есть" if avatar_image_path else "не найден"
        profile_text += (
            "\n🖼 <b>Оформление:</b>\n"
            f"Аватар: {html.escape(avatar_name)}\n"
            f"Цитата: {quote_line}\n"
            f"Файл аватара: {avatar_file_line}"
        )

        await callback.message.edit_text(profile_text, reply_markup=get_profile_menu(), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "profile_stats")
async def profile_stats_callback(callback: CallbackQuery):
    """Детальная статистика"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        stats_text = (
            f"📊 <b>Детальная статистика</b>\n\n"
            f"<b>Основное:</b>\n"
            f"⭐ Уровень: {user.level}\n"
            f"📈 Опыт: {user.experience}/{user.experience_to_next}\n"
            f"💎 Очки: {user.points}\n"
            f"📅 Зарегистрирован: {user.created_at.strftime('%d.%m.%Y') if user.created_at else 'Неизвестно'}\n\n"
            f"<b>PvP:</b>\n"
            f"🏆 Побед: {user.pvp_wins}\n"
            f"💀 Поражений: {user.pvp_losses}\n"
            f"📊 Winrate: {user.get_win_rate()}%\n\n"
            f"<b>PvE:</b>\n"
            f"👹 Побед: {user.pve_wins}\n"
            f"💀 Поражений: {user.pve_losses}\n\n"
            f"<b>Общее:</b>\n"
            f"⚔️ Всего боев: {user.total_battles}"
        )
        
        from keyboards.main_menu import get_back_button
        await callback.message.edit_text(stats_text, reply_markup=get_back_button("profile"), parse_mode="HTML")
    await callback.answer()

@router.callback_query(F.data == "my_deck")
async def my_deck_callback(callback: CallbackQuery):
    """Моя колода"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем экипированные карты
        main_card = None
        support_card = None
        
        if user.slot_1_card_id:
            result = await session.execute(
                select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.id == user.slot_1_card_id)
            )
            main_card = result.scalar_one_or_none()
        
        if user.slot_2_card_id:
            result = await session.execute(
                select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.id == user.slot_2_card_id)
            )
            support_card = result.scalar_one_or_none()
        
        deck_text = "🎴 <b>Моя колода</b>\n\n"
        
        if main_card and main_card.card_template:
            deck_text += (
                f"👑 <b>Главный персонаж:</b>\n"
                f"{main_card.card_template.name} (Lv.{main_card.level})\n"
                f"❤️ HP: {main_card.max_hp} | ⚔️ АТК: {main_card.attack}\n"
                f"🛡️ ЗЩТ: {main_card.defense} | 💨 СКР: {main_card.speed}\n\n"
            )
        else:
            deck_text += "👑 <b>Главный персонаж:</b> Не выбран\n\n"
        
        if support_card and support_card.card_template:
            deck_text += (
                f"🛡️ <b>Поддержка:</b>\n"
                f"{support_card.card_template.name} (Lv.{support_card.level})\n"
                f"❤️ HP: {support_card.max_hp} | ⚔️ АТК: {support_card.attack}\n"
                f"🛡️ ЗЩТ: {support_card.defense} | 💨 СКР: {support_card.speed}\n\n"
            )
        else:
            deck_text += "🛡️ <b>Поддержка:</b> Не выбран\n\n"
        
        if main_card or support_card:
            total_power = 0
            if main_card:
                total_power += main_card.get_total_power()
            if support_card:
                total_power += support_card.get_total_power()
            deck_text += f"💪 <b>Общая сила колоды:</b> {total_power}"
        
        await callback.message.edit_text(
            deck_text, 
            reply_markup=get_deck_keyboard(main_card, support_card),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("select_main_card"))
async def select_main_card_callback(callback: CallbackQuery):
    """Выбор главной карты"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем все карты пользователя
        result = await session.execute(
            select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.user_id == user.id)
        )
        cards = result.scalars().all()
        
        # Фильтруем только персонажей
        character_cards = [c for c in cards if c.card_template and is_character_template(c.card_template)]
        
        if not character_cards:
            await callback.answer("У тебя нет карт персонажей!", show_alert=True)
            return
        
        from keyboards.cards import get_card_selection_keyboard
        await callback.message.edit_text(
            "👑 <b>Выбери главного персонажа:</b>",
            reply_markup=get_card_selection_keyboard(character_cards, "main"),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("select_support_card"))
async def select_support_card_callback(callback: CallbackQuery):
    """Выбор карты поддержки"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Получаем все карты пользователя
        result = await session.execute(
            select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.user_id == user.id)
        )
        cards = result.scalars().all()
        
        # Фильтруем только поддержку
        support_cards = [c for c in cards if c.card_template and is_support_template(c.card_template)]
        
        if not support_cards:
            await callback.answer("У тебя нет карт поддержки!", show_alert=True)
            return
        
        from keyboards.cards import get_card_selection_keyboard
        await callback.message.edit_text(
            "🛡️ <b>Выбери карту поддержки:</b>",
            reply_markup=get_card_selection_keyboard(support_cards, "support"),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("select_card_"))
async def confirm_card_selection_callback(callback: CallbackQuery):
    """Подтверждение выбора карты"""
    parts = callback.data.split("_")
    slot_type = parts[2]  # main или support
    card_id = int(parts[3])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        # Проверяем, что карта принадлежит пользователю
        result = await session.execute(
            select(UserCard).where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()
        
        if not card:
            await callback.answer("Карта не найдена!", show_alert=True)
            return
        
        # Снимаем экипировку с предыдущей карты
        if slot_type == "main" and user.slot_1_card_id:
            result = await session.execute(
                select(UserCard).where(UserCard.id == user.slot_1_card_id)
            )
            old_card = result.scalar_one_or_none()
            if old_card:
                old_card.is_equipped = False
                old_card.slot_number = None
        
        elif slot_type == "support" and user.slot_2_card_id:
            result = await session.execute(
                select(UserCard).where(UserCard.id == user.slot_2_card_id)
            )
            old_card = result.scalar_one_or_none()
            if old_card:
                old_card.is_equipped = False
                old_card.slot_number = None
        
        # Экипируем новую карту
        card.is_equipped = True
        card.slot_number = 1 if slot_type == "main" else 2
        
        if slot_type == "main":
            user.slot_1_card_id = card_id
        else:
            user.slot_2_card_id = card_id
        
        await session.commit()
        
        await callback.answer(f"Карта экипирована!" if slot_type == "main" else "Поддержка выбрана!")
        
        # Обновляем отображение колоды
        await my_deck_callback(callback)


@router.callback_query(F.data.startswith("select_page_"))
async def select_page_callback(callback: CallbackQuery):
    """Пагинация выбора карты для слота"""
    parts = callback.data.split("_")
    slot_type = parts[2]
    page = int(parts[3])

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        result = await session.execute(
            select(UserCard).options(selectinload(UserCard.card_template)).where(UserCard.user_id == user.id)
        )
        cards = result.scalars().all()

        from keyboards.cards import get_card_selection_keyboard
        title = "👑 <b>Выбери главного персонажа:</b>" if slot_type == "main" else "🛡️ <b>Выбери карту поддержки:</b>"
        await callback.message.edit_text(
            title,
            reply_markup=get_card_selection_keyboard(cards, slot_type, page),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("unequip_card_"))
async def unequip_card_callback(callback: CallbackQuery):
    """Снять карту"""
    card_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(UserCard).where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()
        
        if card:
            card.is_equipped = False
            card.slot_number = None
            
            if user.slot_1_card_id == card_id:
                user.slot_1_card_id = None
            elif user.slot_2_card_id == card_id:
                user.slot_2_card_id = None
            
            await session.commit()
            await callback.answer("Карта снята!")
        
        await my_deck_callback(callback)

@router.callback_query(F.data == "difficulty_menu")
async def difficulty_menu_callback(callback: CallbackQuery):
    """Меню выбора сложности"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        diff_emojis = {
            "easy": "🟢",
            "normal": "🔵",
            "hard": "🟠",
            "hardcore": "🔴"
        }
        
        current = diff_emojis.get(user.difficulty, "🔵")
        
        await callback.message.edit_text(
            f"⚙️ <b>Уровень Сложности</b>\n\n"
            f"Текущий: {current} <b>{user.difficulty.upper()}</b>\n"
            f"Множитель наград: {user.get_difficulty_multiplier()}x\n\n"
            f"🟢 <b>Легкий</b> - 0.5x награды, нет штрафов\n"
            f"🔵 <b>Нормальный</b> - 1x награды (стандарт)\n"
            f"🟠 <b>Сложный</b> - 1.5x награды, сильные враги\n"
            f"🔴 <b>Хардкор</b> - 2x награды, смерть = конец\n\n"
            f"Выбери новый уровень:",
            reply_markup=get_difficulty_menu(),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("set_difficulty_"))
async def set_difficulty_callback(callback: CallbackQuery):
    """Установить уровень сложности"""
    difficulty = callback.data.split("_")[2]
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        user.difficulty = difficulty
        user.hardcore_mode = (difficulty == "hardcore")
        
        await session.commit()
        
        await callback.answer(f"Сложность изменена на {difficulty.upper()}!")
        await difficulty_menu_callback(callback)


def _profile_avatar_keyboard(cards: list[UserCard], current_avatar_id: int | None, page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(cards) + PROFILE_PAGE_SIZE - 1) // PROFILE_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * PROFILE_PAGE_SIZE
    end = start + PROFILE_PAGE_SIZE
    page_cards = cards[start:end]

    rows = []
    for card in page_cards:
        if not card.card_template:
            continue
        marker = "✅ " if current_avatar_id == card.id else ""
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker}{card.card_template.name} (Lv.{card.level})",
                    callback_data=f"profile_set_avatar_{card.id}_{page}",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"profile_avatar_menu_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"profile_avatar_menu_{page + 1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton(text="♻️ Сбросить аватар", callback_data="profile_avatar_clear")])
    rows.append([InlineKeyboardButton(text="🔙 К оформлению", callback_data="profile_customization")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _profile_quotes_keyboard(quotes: list[UserQuote], selected_quote: str | None, page: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (len(quotes) + QUOTE_PAGE_SIZE - 1) // QUOTE_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * QUOTE_PAGE_SIZE
    end = start + QUOTE_PAGE_SIZE
    page_quotes = quotes[start:end]

    rows = []
    for quote in page_quotes:
        marker = "✅ " if selected_quote and selected_quote == quote.quote_text else ""
        preview = _quote_preview(quote.quote_text, max_len=50)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{marker}{preview}",
                    callback_data=f"profile_set_quote_{quote.id}_{page}",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"profile_quote_menu_{page - 1}"))
    nav.append(InlineKeyboardButton(text=f"📄 {page + 1}/{total_pages}", callback_data="noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"profile_quote_menu_{page + 1}"))
    rows.append(nav)

    rows.append([InlineKeyboardButton(text="♻️ Сбросить цитату", callback_data="profile_quote_clear")])
    rows.append([InlineKeyboardButton(text="🔙 К оформлению", callback_data="profile_customization")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _render_avatar_menu(callback: CallbackQuery, page: int):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        profile_settings, _, _, changed = await _load_profile_state(session, user)
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.user_id == user.id)
        )
        all_cards = result.scalars().all()
        character_cards = [card for card in all_cards if card.card_template and is_character_template(card.card_template)]
        character_cards.sort(key=lambda card: (card.level, card.id), reverse=True)

        if changed:
            await session.commit()

        if not character_cards:
            await callback.answer("У тебя нет карт персонажей для аватарки.", show_alert=True)
            await _render_profile_customization(callback)
            return

        current_avatar_name = "Стандартный"
        if profile_settings.avatar_card_id:
            current_avatar = next((c for c in character_cards if c.id == profile_settings.avatar_card_id), None)
            if current_avatar and current_avatar.card_template:
                current_avatar_name = current_avatar.card_template.name

        await callback.message.edit_text(
            "🖼 <b>Выбор аватара</b>\n\n"
            "Можно поставить только персонажа, который уже есть у тебя в инвентаре.\n\n"
            f"Текущий аватар: <b>{html.escape(current_avatar_name)}</b>\n"
            f"Доступно персонажей: <b>{len(character_cards)}</b>",
            reply_markup=_profile_avatar_keyboard(character_cards, profile_settings.avatar_card_id, page),
            parse_mode="HTML",
        )


async def _render_quote_menu(callback: CallbackQuery, page: int):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        granted_quotes = await ensure_quotes_for_owned_cards(session, user.id)
        profile_settings, _, _, changed = await _load_profile_state(session, user)
        result = await session.execute(
            select(UserQuote)
            .where(UserQuote.user_id == user.id)
            .order_by(UserQuote.obtained_at.desc(), UserQuote.id.desc())
        )
        quotes = result.scalars().all()

        if granted_quotes or changed:
            await session.commit()

        if not quotes:
            await callback.answer("Пока нет открытых цитат. Получай карты и уровни.", show_alert=True)
            await _render_profile_customization(callback)
            return

        selected_quote = (profile_settings.favorite_quote or "").strip() or None
        selected_preview = html.escape(_quote_preview(selected_quote)) if selected_quote else "не выбрана"

        await callback.message.edit_text(
            "💬 <b>Выбор цитаты</b>\n\n"
            "Выбери одну из открытых цитат. Свой текст вводить нельзя.\n\n"
            f"Текущая цитата: {selected_preview if selected_quote else 'не выбрана'}\n"
            f"Открыто цитат: <b>{len(quotes)}</b>",
            reply_markup=_profile_quotes_keyboard(quotes, selected_quote, page),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "profile_customization")
async def profile_customization_callback(callback: CallbackQuery):
    await _render_profile_customization(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("profile_avatar_menu_"))
async def profile_avatar_menu_callback(callback: CallbackQuery):
    try:
        page = int(callback.data.rsplit("_", 1)[1])
    except ValueError:
        page = 0
    await _render_avatar_menu(callback, page)
    await callback.answer()


@router.callback_query(F.data.startswith("profile_set_avatar_"))
async def profile_set_avatar_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("Некорректный выбор аватара.", show_alert=True)
        return

    try:
        card_id = int(parts[3])
        page = int(parts[4])
    except ValueError:
        await callback.answer("Некорректный выбор аватара.", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        selected_card = result.scalar_one_or_none()
        if not selected_card or not selected_card.card_template or not is_character_template(selected_card.card_template):
            await callback.answer("Для аватара можно выбрать только свою карту персонажа.", show_alert=True)
            return

        profile_settings = await _get_or_create_user_profile(session, user.id)
        profile_settings.avatar_card_id = selected_card.id
        await session.commit()

    await _render_avatar_menu(callback, page)
    await callback.answer("Аватар обновлён.")


@router.callback_query(F.data == "profile_avatar_clear")
async def profile_avatar_clear_callback(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        profile_settings = await _get_or_create_user_profile(session, user.id)
        profile_settings.avatar_card_id = None
        await session.commit()

    await _render_profile_customization(callback)
    await callback.answer("Аватар сброшен.")


@router.callback_query(F.data.startswith("profile_quote_menu_"))
async def profile_quote_menu_callback(callback: CallbackQuery):
    try:
        page = int(callback.data.rsplit("_", 1)[1])
    except ValueError:
        page = 0
    await _render_quote_menu(callback, page)
    await callback.answer()


@router.callback_query(F.data.startswith("profile_set_quote_"))
async def profile_set_quote_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    if len(parts) < 5:
        await callback.answer("Некорректный выбор цитаты.", show_alert=True)
        return

    try:
        quote_id = int(parts[3])
        page = int(parts[4])
    except ValueError:
        await callback.answer("Некорректный выбор цитаты.", show_alert=True)
        return

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        result = await session.execute(
            select(UserQuote).where(UserQuote.id == quote_id, UserQuote.user_id == user.id)
        )
        selected_quote = result.scalar_one_or_none()
        if not selected_quote:
            await callback.answer("Цитата недоступна.", show_alert=True)
            return

        profile_settings = await _get_or_create_user_profile(session, user.id)
        profile_settings.favorite_quote = selected_quote.quote_text
        await session.commit()

    await _render_quote_menu(callback, page)
    await callback.answer("Цитата обновлена.")


@router.callback_query(F.data == "profile_quote_clear")
async def profile_quote_clear_callback(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        profile_settings = await _get_or_create_user_profile(session, user.id)
        profile_settings.favorite_quote = None
        await session.commit()

    await _render_profile_customization(callback)
    await callback.answer("Цитата сброшена.")
