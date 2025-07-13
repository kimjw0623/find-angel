from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Index, JSON, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from contextlib import contextmanager
import threading
from datetime import datetime
from src.database.base_database import BaseDatabaseManager

CacheBase = declarative_base()

class MarketPriceCache(CacheBase):
    __tablename__ = 'market_price_cache'
    
    id = Column(Integer, primary_key=True)
    cache_id = Column(String, nullable=False, unique=True)
    search_cycle_id = Column(String, nullable=False)  # timestamp를 search_cycle_id로 변경
    is_active = Column(Boolean, nullable=False, default=False)
    
    accessory_patterns = relationship("AccessoryPricePattern", back_populates="cache")
    bracelet_patterns = relationship("BraceletPricePattern", back_populates="cache")

class AccessoryPricePattern(CacheBase):
    __tablename__ = 'accessory_price_patterns'
    
    id = Column(Integer, primary_key=True)
    cache_id = Column(String, ForeignKey('market_price_cache.cache_id'), nullable=False)
    grade = Column(String, nullable=False)
    part = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    pattern_key = Column(String, nullable=False)
    role = Column(String, nullable=False)
    
    quality_prices = Column(SQLiteJSON)  # {"60": price, "70": price, "80": price, "90": price}
    total_sample_count = Column(Integer, nullable=False)
    common_option_values = Column(SQLiteJSON)
    
    cache = relationship("MarketPriceCache", back_populates="accessory_patterns")

    __table_args__ = (
        Index('idx_acc_pattern_search', 'cache_id', 'grade', 'part', 'level', 'pattern_key', 'role'),
    )

class BraceletPricePattern(CacheBase):
    __tablename__ = 'bracelet_price_patterns'
    
    id = Column(Integer, primary_key=True)
    cache_id = Column(String, ForeignKey('market_price_cache.cache_id'), nullable=False)
    grade = Column(String, nullable=False)
    pattern_type = Column(String, nullable=False)
    combat_stats = Column(String)
    base_stats = Column(String)
    extra_slots = Column(String)
    price = Column(Integer, nullable=False)
    total_sample_count = Column(Integer, nullable=False)  # Added field
    
    cache = relationship("MarketPriceCache", back_populates="bracelet_patterns")

    __table_args__ = (
        Index('idx_bracelet_pattern_search', 'cache_id', 'grade', 'pattern_type'),
    )

class PatternDatabaseManager(BaseDatabaseManager):
    def get_database_url(self) -> str:
        return 'sqlite:///lostark_cache.db'
    
    def get_base_metadata(self):
        return CacheBase.metadata

