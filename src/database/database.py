from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from contextlib import contextmanager
import threading
from datetime import datetime
import os
from base_database import BaseDatabaseManager

Base = declarative_base()

class PriceRecord(Base):
    __tablename__ = 'price_records'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    search_cycle_id = Column(String, nullable=False, index=True)  # 새로 추가
    grade = Column(String, nullable=False, index=True)  # 고대/유물
    name = Column(String, nullable=False)
    part = Column(String, nullable=False, index=True)   # 목걸이/귀걸이/반지
    level = Column(Integer, nullable=False, index=True)  # 연마 단계
    quality = Column(Integer, nullable=False, index=True)
    trade_count = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    end_time = Column(DateTime, nullable=False)
    damage_increment = Column(Float, nullable=True)  # 딜러용일 경우
    
    options = relationship("ItemOption", back_populates="price_record")
    raw_options = relationship("RawItemOption", back_populates="price_record")

    # 자주 사용될 복합 인덱스 추가
    __table_args__ = (
        Index('idx_grade_part_level', 'grade', 'part', 'level'),
        Index('idx_recent_items', 'timestamp', 'grade', 'part'),
    )

class ItemOption(Base):
    __tablename__ = 'item_options'
    
    id = Column(Integer, primary_key=True)
    price_record_id = Column(Integer, ForeignKey('price_records.id'), index=True)
    option_name = Column(String, nullable=False, index=True)
    option_grade = Column(Integer, nullable=False)
    
    price_record = relationship("PriceRecord", back_populates="options")

    __table_args__ = (
        Index('idx_option_search', 'price_record_id', 'option_name', 'option_grade'),
    )

class RawItemOption(Base):
    __tablename__ = 'raw_item_options'
    
    id = Column(Integer, primary_key=True)
    price_record_id = Column(Integer, ForeignKey('price_records.id'), index=True)
    option_name = Column(String, nullable=False)
    option_value = Column(Float, nullable=False)
    is_percentage = Column(Boolean, nullable=False)
    
    price_record = relationship("PriceRecord", back_populates="raw_options")

class BraceletPriceRecord(Base):
    __tablename__ = 'bracelet_price_records'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    search_cycle_id = Column(String, nullable=False, index=True)  # 새로 추가
    grade = Column(String, nullable=False, index=True)  # 고대/유물
    name = Column(String, nullable=False)
    trade_count = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    end_time = Column(DateTime, nullable=False)
    fixed_option_count = Column(Integer, nullable=False)  # 1 또는 2
    extra_option_count = Column(Integer, nullable=False)
    
    combat_stats = relationship("BraceletCombatStat", back_populates="bracelet")
    base_stats = relationship("BraceletBaseStat", back_populates="bracelet")
    special_effects = relationship("BraceletSpecialEffect", back_populates="bracelet")

    __table_args__ = (
        Index('idx_bracelet_search', 'timestamp', 'grade', 'fixed_option_count'),
    )

class BraceletCombatStat(Base):
    __tablename__ = 'bracelet_combat_stats'
    
    id = Column(Integer, primary_key=True)
    bracelet_id = Column(Integer, ForeignKey('bracelet_price_records.id'), index=True)
    stat_type = Column(String, nullable=False)  # 특화/치명/신속
    value = Column(Integer, nullable=False)
    
    bracelet = relationship("BraceletPriceRecord", back_populates="combat_stats")

    __table_args__ = (
        Index('idx_combat_stat_search', 'bracelet_id', 'stat_type', 'value'),
    )

class BraceletBaseStat(Base):
    __tablename__ = 'bracelet_base_stats'
    
    id = Column(Integer, primary_key=True)
    bracelet_id = Column(Integer, ForeignKey('bracelet_price_records.id'), index=True)
    stat_type = Column(String, nullable=False)  # 힘/민첩/지능
    value = Column(Integer, nullable=False)
    
    bracelet = relationship("BraceletPriceRecord", back_populates="base_stats")

    __table_args__ = (
        Index('idx_base_stat_search', 'bracelet_id', 'stat_type', 'value'),
    )

class BraceletSpecialEffect(Base):
    __tablename__ = 'bracelet_special_effects'
    
    id = Column(Integer, primary_key=True)
    bracelet_id = Column(Integer, ForeignKey('bracelet_price_records.id'), index=True)
    effect_type = Column(String, nullable=False)
    value = Column(Float, nullable=True)
    
    bracelet = relationship("BraceletPriceRecord", back_populates="special_effects")

    __table_args__ = (
        # 특정 팔찌의 특수 효과를 효과 타입별로 빠르게 조회
        Index('idx_bracelet_effect', 'bracelet_id', 'effect_type'),
        # 특정 효과와 값으로 검색할 때 사용
        Index('idx_effect_value', 'effect_type', 'value'),
    )

class DatabaseManager(BaseDatabaseManager):
    def get_database_url(self) -> str:
        return 'sqlite:///lostark_prices.db'
    
    def get_base_metadata(self):
        return Base.metadata

def init_database():
    """데이터베이스 초기 설정 및 테이블 생성"""
    db_manager = DatabaseManager()
    return db_manager