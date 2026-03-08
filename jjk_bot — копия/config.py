"""
Конфигурация бота
"""
import os
from dotenv import load_dotenv

load_dotenv()

# Токен бота (получить у @BotFather)
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")

# Настройки игры
EXP_PER_MESSAGE = 1  # Опыт за сообщение
EXP_COOLDOWN = 30  # Секунд между получением опыта за сообщения

# Настройки PvE
PVE_COOLDOWN = 60  # Секунд между PvE боями
PVP_COOLDOWN = 120  # Секунд между PvP боями

# Настройки наград
EXP_PER_PVE_WIN = 20  # Базовый опыт за PvE
POINTS_PER_PVE_WIN = 2  # Базовые очки за PvE
EXP_PER_PVP_WIN = 50  # Опыт за PvP
POINTS_PER_PVP_WIN = 5  # Очки за PvP
POINTS_PER_LEVEL_UP = 10  # Очки за повышение уровня
COINS_PER_LEVEL_UP = 100  # Монеты за повышение уровня

# Множители сложности
DIFFICULTY_MULTIPLIERS = {
    "easy": 0.5,
    "normal": 1.0,
    "hard": 1.5,
    "hardcore": 2.0
}

# Настройки ежедневных наград
DAILY_REWARDS = {
    1: {"exp": 50, "points": 5, "coins": 100, "name": "День 1"},
    2: {"exp": 75, "points": 8, "coins": 150, "name": "День 2"},
    3: {"exp": 100, "points": 10, "coins": 200, "name": "День 3"},
    4: {"exp": 125, "points": 12, "coins": 250, "name": "День 4"},
    5: {"exp": 150, "points": 15, "coins": 300, "name": "День 5"},
    6: {"exp": 200, "points": 20, "coins": 400, "name": "День 6"},
    7: {"exp": 500, "points": 50, "coins": 1000, "card_chance": 0.3, "name": "День 7 - БОНУС!"}
}

# Настройки техникума
ACADEMY_BASE_COST = 500  # Базовая стоимость обучения
ACADEMY_COST_INCREASE = 100  # Увеличение стоимости за посещение
ACADEMY_COOLDOWN_HOURS = 24  # Кулдаун между посещениями

# Настройки рынка
MARKET_TAX = 0.1  # Комиссия рынка (10%)
MIN_PRICE = 50  # Минимальная цена
MAX_PRICE = 10000000  # Максимальная цена

# Шансы черной молнии по умолчанию
BLACK_FLASH_CHANCES = {
    "common": 2,
    "rare": 5,
    "epic": 10,
    "legendary": 15,
    "mythical": 20
}

# Стартовые ресурсы
STARTER_COINS = 1000
STARTER_POINTS = 0

ADMINS = [123456789]
# ID администраторов (список telegram ID)
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]