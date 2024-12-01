from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Index, JSON, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.dialects.sqlite import JSON as SQLiteJSON
from contextlib import contextmanager
import threading
from datetime import datetime

CacheBase = declarative_base()

class MarketPriceCache(CacheBase):
    __tablename__ = 'market_price_cache'
    
    id = Column(Integer, primary_key=True)
    cache_id = Column(String, nullable=False, unique=True)
    timestamp = Column(DateTime, nullable=False)
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
    
    base_price = Column(Integer, nullable=False)
    price_std = Column(Float, nullable=False)
    quality_coefficient = Column(Float, nullable=False)
    trade_count_coefficient = Column(Float, nullable=False)
    sample_count = Column(Integer, nullable=False)
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
    
    cache = relationship("MarketPriceCache", back_populates="bracelet_patterns")

    __table_args__ = (
        Index('idx_bracelet_pattern_search', 'cache_id', 'grade', 'pattern_type'),
    )

class CacheDBManager:
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance.engine = create_engine('sqlite:///lostark_cache.db')
                    # WAL 모드 활성화로 읽기/쓰기 동시성 개선
                    with cls._instance.engine.connect() as conn:
                        conn.execute(text("PRAGMA journal_mode=WAL"))
                    cls._instance.Session = sessionmaker(bind=cls._instance.engine)
                    # 데이터베이스 및 테이블 생성
                    CacheBase.metadata.create_all(cls._instance.engine)
        return cls._instance

    @contextmanager
    def get_session(self):
        """일반 세션을 생성하고 자동으로 닫아주는 컨텍스트 매니저"""
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    @contextmanager
    def get_read_session(self):
        """읽기 전용 세션 - 다른 읽기 작업과 동시 실행 가능"""
        session = self.Session()
        try:
            session.execute(text("BEGIN"))
            yield session
        finally:
            session.rollback()  # 읽기 전용이므로 rollback으로 트랜잭션 종료
            session.close()

    @contextmanager
    def get_write_session(self):
        """쓰기 세션 - 더 엄격한 락킹 적용"""
        with self._lock:  # 스레드 레벨 락킹
            session = self.Session()
            try:
                session.execute(text("BEGIN EXCLUSIVE"))
                yield session
                session.commit()
            except Exception as e:
                session.rollback()
                raise e
            finally:
                session.close()

def init_cache_database():
    """캐시 데이터베이스 초기 설정 및 테이블 생성"""
    db_manager = CacheDBManager()
    return db_manager