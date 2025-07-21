from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Index, JSON, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from contextlib import contextmanager
import threading
from datetime import datetime
from src.database.base_database import BaseDatabaseManager

PatternBase = declarative_base()

class AuctionPricePattern(PatternBase):
    __tablename__ = 'auction_price_pattern'
    
    id = Column(Integer, primary_key=True)
    pattern_id = Column(String, nullable=False, unique=True)
    search_cycle_id = Column(String, nullable=False)  # timestamp를 search_cycle_id로 변경
    is_active = Column(Boolean, nullable=False, default=False)
    
    accessory_patterns = relationship("AccessoryPricePattern", back_populates="pattern")
    bracelet_patterns = relationship("BraceletPricePattern", back_populates="pattern")

class AccessoryPricePattern(PatternBase):
    __tablename__ = 'accessory_price_patterns'
    
    id = Column(Integer, primary_key=True)
    pattern_id = Column(String, ForeignKey('auction_price_pattern.pattern_id'), nullable=False)
    grade = Column(String, nullable=False)
    part = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    pattern_key = Column(String, nullable=False)
    role = Column(String, nullable=False)
    
    quality_prices = Column(SQLiteJSON)  # {"60": price, "70": price, "80": price, "90": price}
    total_sample_count = Column(Integer, nullable=False)
    common_option_values = Column(SQLiteJSON)
    
    pattern = relationship("AuctionPricePattern", back_populates="accessory_patterns")

    __table_args__ = (
        Index('idx_acc_pattern_search', 'pattern_id', 'grade', 'part', 'level', 'pattern_key', 'role'),
    )

class BraceletPricePattern(PatternBase):
    __tablename__ = 'bracelet_price_patterns'
    
    id = Column(Integer, primary_key=True)
    pattern_id = Column(String, ForeignKey('auction_price_pattern.pattern_id'), nullable=False)
    grade = Column(String, nullable=False)
    pattern_type = Column(String, nullable=False)
    combat_stats = Column(String)
    base_stats = Column(String)
    extra_slots = Column(String)
    price = Column(Integer, nullable=False)
    total_sample_count = Column(Integer, nullable=False)  # Added field
    
    pattern = relationship("AuctionPricePattern", back_populates="bracelet_patterns")

    __table_args__ = (
        Index('idx_bracelet_pattern_search', 'pattern_id', 'grade', 'pattern_type'),
    )

class PatternDatabaseManager(BaseDatabaseManager):
    def get_database_url(self) -> str:
        return 'sqlite:///lostark_pattern.db'
    
    def get_base_metadata(self):
        return PatternBase.metadata

