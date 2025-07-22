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
    
    # 모델 타입 및 기본 정보
    model_type = Column(String, nullable=False, default='multilinear')  # 'multilinear' 또는 'minimum_price'
    base_price = Column(Integer, nullable=False)       # 최저가 또는 기본 가격
    total_sample_count = Column(Integer, nullable=False)
    r_squared = Column(Float, nullable=True)           # 모델 성능 지표
    success_rate = Column(Float, nullable=True)        # 판매 성공률 (%)
    sold_count = Column(Integer, nullable=True)        # 판매된 아이템 수
    expired_count = Column(Integer, nullable=True)     # 만료된 아이템 수
    
    # Multilinear regression 모델 데이터 (model_type='multilinear'일 때만 사용)
    intercept = Column(Float, nullable=True)           # 절편
    coefficients = Column(SQLiteJSON, nullable=True)   # 계수 벡터 {feature_name: coefficient}
    feature_names = Column(SQLiteJSON, nullable=True)  # 피처 순서 [힘민지, 깡공, ...]
    
    pattern = relationship("AuctionPricePattern", back_populates="accessory_patterns")

    __table_args__ = (
        # 메인 검색용: 시간 + 기본 필터
        Index('idx_acc_datetime_grade_part', 'pattern_datetime', 'grade', 'part', 'level'),
        # 패턴 조회용: 역할별 패턴 검색
        Index('idx_acc_pattern_role', 'grade', 'part', 'pattern_key', 'role'),
        # 성능 분석용: R² 기준 정렬
        Index('idx_acc_performance', 'r_squared', 'success_rate'),
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
    success_rate = Column(Float, nullable=True)  # 판매 성공률 (%)
    sold_count = Column(Integer, nullable=True)  # 판매된 아이템 수
    expired_count = Column(Integer, nullable=True)  # 만료된 아이템 수
    
    pattern = relationship("AuctionPricePattern", back_populates="bracelet_patterns")

    __table_args__ = (
        # 메인 검색용: 시간 + 등급 + 스탯 패턴
        Index('idx_bracelet_datetime_grade', 'pattern_datetime', 'grade', 'sorted_stats'),
        # 성능 분석용: 판매 성공률 기준 정렬
        Index('idx_bracelet_performance', 'success_rate', 'price'),
        # 가격 범위 검색용: 등급별 가격 정렬
        Index('idx_bracelet_price', 'grade', 'price'),
    )

class PatternDatabaseManager(BaseDatabaseManager):
    def get_database_url(self) -> str:
        return 'sqlite:///lostark_pattern.db'
    
    def get_base_metadata(self):
        return PatternBase.metadata

