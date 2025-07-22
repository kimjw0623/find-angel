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
    
    pattern_datetime = Column(DateTime, primary_key=True)
    is_active = Column(Boolean, nullable=False, default=False)
    
    accessory_patterns = relationship("AccessoryPricePattern", back_populates="pattern")
    bracelet_patterns = relationship("BraceletPricePattern", back_populates="pattern")

class AccessoryPricePattern(PatternBase):
    __tablename__ = 'accessory_price_patterns'
    
    id = Column(Integer, primary_key=True)
    pattern_datetime = Column(DateTime, ForeignKey('auction_price_pattern.pattern_datetime'), nullable=False)
    grade = Column(String, nullable=False)
    part = Column(String, nullable=False)
    level = Column(Integer, nullable=False)
    pattern_key = Column(String, nullable=False)
    role = Column(String, nullable=False)
    
    # Multilinear regression 모델 데이터
    intercept = Column(Float, nullable=False)          # 절편 (base_price)
    coefficients = Column(SQLiteJSON, nullable=False)  # 계수 벡터 {feature_name: coefficient}
    feature_names = Column(SQLiteJSON, nullable=False)  # 피처 순서 [힘민지, 깡공, ...]
    total_sample_count = Column(Integer, nullable=False)
    
    pattern = relationship("AuctionPricePattern", back_populates="accessory_patterns")

    __table_args__ = (
        Index('idx_acc_pattern_search', 'pattern_datetime', 'grade', 'part', 'level', 'pattern_key', 'role'),
    )

class BraceletPricePattern(PatternBase):
    __tablename__ = 'bracelet_price_patterns'
    
    id = Column(Integer, primary_key=True)
    pattern_datetime = Column(DateTime, ForeignKey('auction_price_pattern.pattern_datetime'), nullable=False)
    grade = Column(String, nullable=False)
    sorted_stats = Column(String, nullable=False)  # 새로운 통합 스탯 필드
    extra_slots = Column(String)
    price = Column(Integer, nullable=False)
    total_sample_count = Column(Integer, nullable=False)
    
    pattern = relationship("AuctionPricePattern", back_populates="bracelet_patterns")

    __table_args__ = (
        Index('idx_bracelet_pattern_search', 'pattern_datetime', 'grade', 'sorted_stats'),
    )

class PatternDatabaseManager(BaseDatabaseManager):
    def get_database_url(self) -> str:
        return 'sqlite:///lostark_pattern.db'
    
    def get_base_metadata(self):
        return PatternBase.metadata

