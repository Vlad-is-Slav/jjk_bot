"""
Данные всех доступных карт в игре
Основано на "Магической битве" (Jujutsu Kaisen)
"""

# Карты персонажей (главные)
CHARACTER_CARDS = [
    # Легендарные
    {
        "name": "Годжо Сатору",
        "description": "Сильнейший маг. Владелец Безграничной и Шести Глаз.",
        "rarity": "legendary",
        "base_attack": 95,
        "base_defense": 80,
        "base_speed": 90,
        "base_hp": 150,
        "growth_multiplier": 1.15
    },
    {
        "name": "Рёмен Сукуна",
        "description": "Король проклятий. Легендарное проклятие.",
        "rarity": "legendary",
        "base_attack": 100,
        "base_defense": 75,
        "base_speed": 85,
        "base_hp": 150,
        "growth_multiplier": 1.15
    },
    {
        "name": "Гето Сугуру",
        "description": "Маг-проклятие. Владелец Кражи духов.",
        "rarity": "epic",
        "base_attack": 85,
        "base_defense": 70,
        "base_speed": 75,
        "base_hp": 120,
        "growth_multiplier": 1.12
    },
    {
        "name": "Итадори Юдзи",
        "description": "Сосуд Сукуны. Обладает невероятной физической силой.",
        "rarity": "epic",
        "base_attack": 75,
        "base_defense": 65,
        "base_speed": 70,
        "base_hp": 130,
        "growth_multiplier": 1.12
    },
    {
        "name": "Фушигуро Мегуми",
        "description": "Владелец Десяти Теней. Такумадау.",
        "rarity": "epic",
        "base_attack": 70,
        "base_defense": 60,
        "base_speed": 75,
        "base_hp": 110,
        "growth_multiplier": 1.11
    },
    {
        "name": "Кугисаки Нобара",
        "description": "Маг с молотком и гвоздями. Стратегический боец.",
        "rarity": "epic",
        "base_attack": 65,
        "base_defense": 55,
        "base_speed": 70,
        "base_hp": 100,
        "growth_multiplier": 1.10
    },
    {
        "name": "Тодо Аой",
        "description": "Мастер боевых искусств. Владелец Бугорка.",
        "rarity": "epic",
        "base_attack": 80,
        "base_defense": 70,
        "base_speed": 65,
        "base_hp": 125,
        "growth_multiplier": 1.11
    },
    {
        "name": "Маки Дзэнин",
        "description": "Мастер оружия. Нулевая целостность.",
        "rarity": "epic",
        "base_attack": 72,
        "base_defense": 60,
        "base_speed": 78,
        "base_hp": 105,
        "growth_multiplier": 1.10
    },
    
    # Редкие
    {
        "name": "Инумаки Тогэ",
        "description": "Наследник Каминого. Речевая магия.",
        "rarity": "rare",
        "base_attack": 55,
        "base_defense": 50,
        "base_speed": 60,
        "base_hp": 90,
        "growth_multiplier": 1.08
    },
    {
        "name": "Панда",
        "description": "Абнормальный труп. Три ядра.",
        "rarity": "rare",
        "base_attack": 60,
        "base_defense": 65,
        "base_speed": 50,
        "base_hp": 110,
        "growth_multiplier": 1.08
    },
    {
        "name": "Нанами Кенто",
        "description": "Бывший офисный работник. Мастер пропорции.",
        "rarity": "rare",
        "base_attack": 62,
        "base_defense": 58,
        "base_speed": 55,
        "base_hp": 95,
        "growth_multiplier": 1.09
    },
    {
        "name": "Мехамару",
        "description": "Управляет куклой на расстоянии.",
        "rarity": "rare",
        "base_attack": 50,
        "base_defense": 45,
        "base_speed": 65,
        "base_hp": 80,
        "growth_multiplier": 1.07
    },
    
    # Обычные
    {
        "name": "Миwa Касуми",
        "description": "Маг-новичок с мечом.",
        "rarity": "common",
        "base_attack": 40,
        "base_defense": 35,
        "base_speed": 45,
        "base_hp": 70,
        "growth_multiplier": 1.05
    },
    {
        "name": "Камо Норitoshi",
        "description": "Наследник Кровавой магии.",
        "rarity": "common",
        "base_attack": 42,
        "base_defense": 38,
        "base_speed": 40,
        "base_hp": 75,
        "growth_multiplier": 1.05
    },
    {
        "name": "Мута Кокичи",
        "description": "Мехамару в кукле.",
        "rarity": "common",
        "base_attack": 35,
        "base_defense": 40,
        "base_speed": 50,
        "base_hp": 65,
        "growth_multiplier": 1.04
    },
]

# Карты поддержки (оружие, шикигами)
SUPPORT_CARDS = [
    # Легендарные
    {
        "name": "Махорага",
        "description": "Восьмикрылый Дивный Генерал. Сильнейший шикигами.",
        "rarity": "legendary",
        "base_attack": 70,
        "base_defense": 60,
        "base_speed": 50,
        "base_hp": 100,
        "growth_multiplier": 1.12
    },
    {
        "name": "Камутадзики",
        "description": "Проклятое оружие Сукуны.",
        "rarity": "legendary",
        "base_attack": 80,
        "base_defense": 30,
        "base_speed": 60,
        "base_hp": 50,
        "growth_multiplier": 1.10
    },
    
    # Эпические
    {
        "name": "Нуэ",
        "description": "Шикигами Фушигуро. Громовая птица.",
        "rarity": "epic",
        "base_attack": 55,
        "base_defense": 40,
        "base_speed": 65,
        "base_hp": 70,
        "growth_multiplier": 1.10
    },
    {
        "name": "Великая Змея",
        "description": "Шикигами Фушигуро. Орочи.",
        "rarity": "epic",
        "base_attack": 50,
        "base_defense": 55,
        "base_speed": 45,
        "base_hp": 85,
        "growth_multiplier": 1.09
    },
    {
        "name": "Проклятый меч",
        "description": "Особого класса проклятое оружие.",
        "rarity": "epic",
        "base_attack": 65,
        "base_defense": 25,
        "base_speed": 40,
        "base_hp": 40,
        "growth_multiplier": 1.08
    },
    {
        "name": "Колесница Серебряного Льва",
        "description": "Шикигами Десяти Теней.",
        "rarity": "epic",
        "base_attack": 45,
        "base_defense": 60,
        "base_speed": 70,
        "base_hp": 80,
        "growth_multiplier": 1.09
    },
    
    # Редкие
    {
        "name": "Пес",
        "description": "Шикигами Фушигуро. Гончая.",
        "rarity": "rare",
        "base_attack": 40,
        "base_defense": 35,
        "base_speed": 55,
        "base_hp": 60,
        "growth_multiplier": 1.07
    },
    {
        "name": "Кролики",
        "description": "Шикигами Фушигуро. Трубадзу.",
        "rarity": "rare",
        "base_attack": 35,
        "base_defense": 30,
        "base_speed": 60,
        "base_hp": 50,
        "growth_multiplier": 1.07
    },
    {
        "name": "Молоток и гвозди",
        "description": "Оружие Кугисаки.",
        "rarity": "rare",
        "base_attack": 50,
        "base_defense": 20,
        "base_speed": 35,
        "base_hp": 30,
        "growth_multiplier": 1.06
    },
    {
        "name": "Кукла Панды",
        "description": "Тело Панды в бою.",
        "rarity": "rare",
        "base_attack": 45,
        "base_defense": 50,
        "base_speed": 40,
        "base_hp": 70,
        "growth_multiplier": 1.07
    },
    
    # Обычные
    {
        "name": "Кукла Мехамару",
        "description": "Дистанционно управляемая кукла.",
        "rarity": "common",
        "base_attack": 30,
        "base_defense": 25,
        "base_speed": 40,
        "base_hp": 45,
        "growth_multiplier": 1.05
    },
    {
        "name": "Катана",
        "description": "Обычный меч мага.",
        "rarity": "common",
        "base_attack": 35,
        "base_defense": 20,
        "base_speed": 30,
        "base_hp": 25,
        "growth_multiplier": 1.04
    },
    {
        "name": "Талисман",
        "description": "Защитный талисман.",
        "rarity": "common",
        "base_attack": 15,
        "base_defense": 40,
        "base_speed": 25,
        "base_hp": 35,
        "growth_multiplier": 1.04
    },
]

# Все карты вместе
ALL_CARDS = CHARACTER_CARDS + SUPPORT_CARDS

# Шансы выпадения по редкости
RARITY_CHANCES = {
    "common": 50,      # 50%
    "rare": 30,        # 30%
    "epic": 15,        # 15%
    "legendary": 4.5,  # 4.5%
    "mythical": 0.5    # 0.5%
}

def get_cards_by_rarity(rarity: str):
    """Получить все карты определенной редкости"""
    return [card for card in ALL_CARDS if card["rarity"] == rarity]

def get_character_cards():
    """Получить только карты персонажей"""
    return CHARACTER_CARDS

def get_support_cards():
    """Получить только карты поддержки"""
    return SUPPORT_CARDS