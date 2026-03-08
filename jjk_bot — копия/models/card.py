from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Float
from sqlalchemy.orm import relationship
from .base import Base

class Card(Base):
    """Шаблон карты (справочник всех доступных карт)"""
    __tablename__ = 'cards'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    
    # Тип карты: 'character' (персонаж), 'support' (поддержка), 'weapon' (оружие), 'artifact' (артефакт), 'pact' (пакт)
    card_type = Column(String(20), default='character')
    
    # Редкость: common, rare, epic, legendary, mythical
    rarity = Column(String(20), default='common')
    
    # Базовые характеристики
    base_attack = Column(Integer, default=10)
    base_defense = Column(Integer, default=10)
    base_speed = Column(Integer, default=10)
    base_hp = Column(Integer, default=100)
    
    # Проклятая энергия
    base_ce = Column(Integer, default=100)  # Базовое количество проклятой энергии
    ce_regen = Column(Integer, default=10)  # Восстановление CE за ход
    
    # Множитель роста характеристик при прокачке
    growth_multiplier = Column(Float, default=1.1)
    
    # Врожденная техника (для 4 слота)
    innate_technique = Column(String(100), nullable=True)
    
    # Способности карты (JSON)
    abilities = Column(String(1000), nullable=True)
    
    # Шанс черной молнии (%)
    black_flash_chance = Column(Float, default=2.0)
    
    # Изображение
    image_url = Column(String(500), nullable=True)
    
    # Связь с картами игроков
    user_cards = relationship("UserCard", back_populates="card_template")


class UserCard(Base):
    """Карта конкретного игрока (с прокачкой)"""
    __tablename__ = 'user_cards'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=False)
    card_id = Column(Integer, ForeignKey('cards.id'), nullable=False)
    
    # Уровень прокачки карты
    level = Column(Integer, default=1)
    
    # Текущие характеристики
    attack = Column(Integer, default=0)
    defense = Column(Integer, default=0)
    speed = Column(Integer, default=0)
    hp = Column(Integer, default=0)
    max_hp = Column(Integer, default=0)
    
    # Проклятая энергия
    ce = Column(Integer, default=0)  # Текущая CE
    max_ce = Column(Integer, default=100)  # Максимальная CE
    
    # Стоимость следующей прокачки
    upgrade_cost = Column(Integer, default=5)
    
    # Экипирована ли карта
    is_equipped = Column(Boolean, default=False)
    
    # В каком слоте (1-4)
    slot_number = Column(Integer, nullable=True)
    
    # Связи
    user = relationship("User", back_populates="cards")
    card_template = relationship("Card", back_populates="user_cards")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.card_template:
            self.recalculate_stats()
    
    def recalculate_stats(self):
        """Пересчитать характеристики на основе уровня"""
        if not self.card_template:
            return
        
        multiplier = self.card_template.growth_multiplier ** (self.level - 1)
        
        self.attack = int(self.card_template.base_attack * multiplier)
        self.defense = int(self.card_template.base_defense * multiplier)
        self.speed = int(self.card_template.base_speed * multiplier)
        self.max_hp = int(self.card_template.base_hp * multiplier)
        self.hp = self.max_hp
        
        self.max_ce = int(self.card_template.base_ce * multiplier)
        self.ce = self.max_ce
        
        # Стоимость прокачки растет с уровнем
        self.upgrade_cost = int(5 * (1.3 ** (self.level - 1)))
    
    def upgrade(self):
        """Прокачать карту на 1 уровень"""
        self.level += 1
        self.recalculate_stats()
        return True
    
    def get_total_power(self):
        """Получить общую силу карты"""
        return self.attack + self.defense + self.speed + self.max_hp // 10 + self.max_ce // 20
    
    def heal(self):
        """Восстановить HP и CE до максимума"""
        self.hp = self.max_hp
        self.ce = self.max_ce
    
    def regen_ce(self):
        """Восстановить CE за ход"""
        if self.card_template:
            self.ce = min(self.max_ce, self.ce + self.card_template.ce_regen)
    
    def take_damage(self, damage: int):
        """Получить урон, учитывая защиту"""
        actual_damage = max(1, int(damage - self.defense * 0.5))
        self.hp = max(0, self.hp - actual_damage)
        return actual_damage
    
    def spend_ce(self, amount: int) -> bool:
        """Потратить CE"""
        if self.ce >= amount:
            self.ce -= amount
            return True
        return False
    
    def is_alive(self):
        """Проверить, жива ли карта"""
        return self.hp > 0
    
    def check_black_flash(self) -> bool:
        """Проверить срабатывание черной молнии"""
        import random
        chance = self.card_template.black_flash_chance if self.card_template else 2.0
        return random.random() * 100 < chance
    
    def get_abilities(self):
        """Получить список способностей карты"""
        if not self.card_template or not self.card_template.abilities:
            return []
        import json
        try:
            return json.loads(self.card_template.abilities)
        except:
            return []