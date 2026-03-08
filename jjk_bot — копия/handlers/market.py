from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from sqlalchemy import select, desc
from sqlalchemy.orm import selectinload

from models import async_session, User, MarketListing, UserCard, Card, TradeOffer

router = Router()

@router.message(Command("market"))
async def cmd_market(message: Message):
    """Команда /market"""
    await message.answer(
        "🏪 <b>Рынок</b>\n\n"
        "Нажми кнопку, чтобы открыть рынок.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏪 Открыть рынок", callback_data="market")]
        ]),
        parse_mode="HTML"
    )

@router.callback_query(F.data == "market")
async def market_menu_callback(callback: CallbackQuery):
    """Меню рынка"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🛒 Купить карту", callback_data="market_buy"),
            InlineKeyboardButton(text="📤 Продать карту", callback_data="market_sell")
        ],
        [
            InlineKeyboardButton(text="🔄 Обмен", callback_data="market_trade"),
            InlineKeyboardButton(text="📋 Мои лоты", callback_data="my_listings")
        ],
        [
            InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")
        ]
    ])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        await callback.message.edit_text(
            f"🏪 <b>Рынок Карт</b>\n\n"
            f"💰 Твои монеты: <b>{user.coins if user else 0}</b>\n\n"
            f"Здесь ты можешь:\n"
            f"🛒 Купить карты у других игроков\n"
            f"📤 Продать свои карты\n"
            f"🔄 Обмениваться картами",
            reply_markup=keyboard,
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data == "market_buy")
async def market_buy_callback(callback: CallbackQuery):
    """Показать лоты на продажу"""
    async with async_session() as session:
        result = await session.execute(
            select(MarketListing)
            .options(selectinload(MarketListing.seller))
            .where(MarketListing.sold == False)
            .order_by(desc(MarketListing.created_at))
            .limit(20)
        )
        listings = result.scalars().all()
        
        if not listings:
            await callback.message.edit_text(
                "🏪 <b>Рынок</b>\n\n"
                "Пока нет активных лотов.\n"
                "Загляни позже или продай свою карту!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="market")]
                ]),
                parse_mode="HTML"
            )
            return
        
        listings_text = "🏪 <b>Доступные карты:</b>\n\n"
        buttons = []
        
        for listing in listings:
            rarity_emoji = {
                "common": "⚪",
                "rare": "🔵",
                "epic": "🟣",
                "legendary": "🟡",
                "mythical": "🔴"
            }.get(listing.item_rarity, "⚪")
            
            listings_text += (
                f"{rarity_emoji} <b>{listing.item_name}</b> (Lv.{listing.item_level})\n"
                f"   💰 Цена: {listing.price} монет\n"
                f"   👤 Продавец: {listing.seller.first_name or 'Игрок'}\n\n"
            )
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"🛒 Купить {listing.item_name[:15]} ({listing.price}🪙)",
                    callback_data=f"buy_listing_{listing.id}"
                )
            ])
        
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="market")])
        
        await callback.message.edit_text(
            listings_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("buy_listing_"))
async def buy_listing_callback(callback: CallbackQuery):
    """Купить лот"""
    listing_id = int(callback.data.split("_")[2])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        buyer = result.scalar_one_or_none()
        
        if not buyer:
            await callback.answer("Сначала используй /start", show_alert=True)
            return
        
        result = await session.execute(
            select(MarketListing)
            .options(selectinload(MarketListing.seller))
            .where(MarketListing.id == listing_id, MarketListing.sold == False)
        )
        listing = result.scalar_one_or_none()
        
        if not listing:
            await callback.answer("Лот не найден или уже продан!", show_alert=True)
            return
        
        if listing.seller_id == buyer.id:
            await callback.answer("Нельзя купить свой лот!", show_alert=True)
            return
        
        if buyer.coins < listing.price:
            await callback.answer("Недостаточно монет!", show_alert=True)
            return
        
        # Переводим монеты
        buyer.coins -= listing.price
        listing.seller.coins += listing.price
        
        # Передаем карту
        result = await session.execute(
            select(UserCard).where(UserCard.id == listing.item_id)
        )
        card = result.scalar_one_or_none()
        
        if card:
            card.user_id = buyer.id
            card.is_equipped = False
            card.slot_number = None
        
        # Обновляем лот
        listing.sold = True
        listing.sold_at = datetime.utcnow()
        listing.buyer_id = buyer.id
        
        await session.commit()
        
        await callback.answer(
            f"✅ Покупка совершена!\n\n"
            f"Карта: {listing.item_name}\n"
            f"Потрачено: {listing.price} монет",
            show_alert=True
        )
        
        await market_buy_callback(callback)

@router.callback_query(F.data == "market_sell")
async def market_sell_callback(callback: CallbackQuery):
    """Продать карту"""
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
            .where(
                UserCard.user_id == user.id,
                UserCard.is_equipped == False
            )
        )
        cards = result.scalars().all()
        
        if not cards:
            await callback.message.edit_text(
                "📤 <b>Продажа карты</b>\n\n"
                "У тебя нет неэкипированных карт для продажи.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="market")]
                ]),
                parse_mode="HTML"
            )
            return
        
        cards_text = "📤 <b>Выбери карту для продажи:</b>\n\n"
        buttons = []
        
        for card in cards:
            card_name = card.card_template.name if card.card_template else "Unknown"
            rarity = card.card_template.rarity if card.card_template else "common"
            
            rarity_emoji = {
                "common": "⚪",
                "rare": "🔵",
                "epic": "🟣",
                "legendary": "🟡",
                "mythical": "🔴"
            }.get(rarity, "⚪")
            
            cards_text += f"{rarity_emoji} {card_name} (Lv.{card.level})\n"
            
            buttons.append([
                InlineKeyboardButton(
                    text=f"💰 Продать {card_name[:15]}",
                    callback_data=f"sell_card_{card.id}"
                )
            ])
        
        buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="market")])
        
        await callback.message.edit_text(
            cards_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("sell_card_"))
async def sell_card_price_callback(callback: CallbackQuery):
    """Установить цену продажи"""
    card_id = int(callback.data.split("_")[2])
    
    # Здесь нужно запросить цену у пользователя
    # Для простоты установим рекомендуемую цену
    
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
        card = result.scalar_one_or_none()
        
        if not card:
            await callback.answer("Карта не найдена!", show_alert=True)
            return
        
        # Рекомендуемая цена
        base_price = {
            "common": 100,
            "rare": 500,
            "epic": 2000,
            "legendary": 10000,
            "mythical": 50000
        }.get(card.card_template.rarity, 100)
        
        level_multiplier = 1 + (card.level - 1) * 0.1
        recommended_price = int(base_price * level_multiplier)
        
        await callback.message.edit_text(
            f"💰 <b>Продажа карты</b>\n\n"
            f"Карта: <b>{card.card_template.name}</b>\n"
            f"Уровень: {card.level}\n"
            f"Редкость: {card.card_template.rarity}\n\n"
            f"Рекомендуемая цена: <b>{recommended_price}</b> монет\n\n"
            f"Отправь цену в чат (только число):",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"💰 По рекомендации ({recommended_price})", callback_data=f"confirm_sell_{card.id}_{recommended_price}")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="market_sell")]
            ]),
            parse_mode="HTML"
        )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_sell_"))
async def confirm_sell_callback(callback: CallbackQuery):
    """Подтвердить продажу"""
    parts = callback.data.split("_")
    card_id = int(parts[2])
    price = int(parts[3])
    
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()
        
        result = await session.execute(
            select(UserCard)
            .options(selectinload(UserCard.card_template))
            .where(UserCard.id == card_id, UserCard.user_id == user.id)
        )
        card = result.scalar_one_or_none()
        
        if not card:
            await callback.answer("Карта не найдена!", show_alert=True)
            return

        result = await session.execute(
            select(MarketListing).where(
                MarketListing.item_id == card.id,
                MarketListing.seller_id == user.id,
                MarketListing.sold == False
            )
        )
        existing_listing = result.scalar_one_or_none()
        if existing_listing:
            await callback.answer("Эта карта уже выставлена на рынок!", show_alert=True)
            return
        
        # Создаем лот
        listing = MarketListing(
            seller_id=user.id,
            listing_type="card",
            item_id=card.id,
            item_name=card.card_template.name,
            item_level=card.level,
            item_rarity=card.card_template.rarity,
            price=price
        )
        session.add(listing)
        await session.commit()
        
        await callback.answer(
            f"✅ Карта выставлена на продажу!\n\n"
            f"{card.card_template.name} - {price} монет",
            show_alert=True
        )
        
        await market_menu_callback(callback)


@router.callback_query(F.data == "my_listings")
async def my_listings_callback(callback: CallbackQuery):
    """Показать лоты текущего игрока"""
    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.telegram_id == callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Сначала используй /start", show_alert=True)
            return

        result = await session.execute(
            select(MarketListing)
            .where(MarketListing.seller_id == user.id)
            .order_by(desc(MarketListing.created_at))
            .limit(20)
        )
        listings = result.scalars().all()

        if not listings:
            await callback.message.edit_text(
                "📋 <b>Мои лоты</b>\n\n"
                "У тебя пока нет лотов на рынке.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Назад", callback_data="market")]
                ]),
                parse_mode="HTML"
            )
            await callback.answer()
            return

        text = "📋 <b>Мои лоты</b>\n\n"
        for listing in listings:
            status = "✅ Продан" if listing.sold else "🟢 Активен"
            text += f"{status} {listing.item_name} (Lv.{listing.item_level}) - {listing.price}🪙\n"

        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Назад", callback_data="market")]
            ]),
            parse_mode="HTML"
        )
    await callback.answer()


@router.callback_query(F.data == "market_trade")
async def market_trade_callback(callback: CallbackQuery):
    """Заглушка для обменов"""
    await callback.message.edit_text(
        "🔄 <b>Обмен картами</b>\n\n"
        "Система обменов в разработке. Пока доступна покупка и продажа на рынке.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Назад", callback_data="market")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


from datetime import datetime
