from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Index, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.types import Enum as SQLEnum
from contextlib import contextmanager
from enum import Enum
import threading
from datetime import datetime
import os
from typing import Optional, Union
import asyncio
from src.database.base_database import BaseDatabaseManager
from src.common.utils import fix_dup_options, number_to_scale

Base = declarative_base()

class AuctionStatus(Enum):
    ACTIVE = 'active'
    SOLD = 'sold'
    EXPIRED = 'expired'

class AuctionAccessory(Base):
    __tablename__ = 'auction_accessories'
    
    id = Column(Integer, primary_key=True)
    grade = Column(String, nullable=False, index=True)  # 고대/유물
    name = Column(String, nullable=False)
    part = Column(String, nullable=False, index=True)   # 목걸이/귀걸이/반지
    level = Column(Integer, nullable=False, index=True)  # 연마 단계
    quality = Column(Integer, nullable=False, index=True)
    price = Column(Integer, nullable=False)
    trade_count = Column(Integer, nullable=False)
    end_time = Column(DateTime, nullable=False)
    first_seen_at = Column(DateTime, nullable=False, index=True)  # 처음 발견된 시간
    last_seen_at = Column(DateTime, nullable=False, index=True)   # 마지막으로 발견된 시간
    sold_at = Column(DateTime, index=True)  # 판매된 것으로 추정되는 시간
    status = Column(SQLEnum(AuctionStatus), nullable=False, index=True, default=AuctionStatus.ACTIVE)
    hp = Column(Integer, nullable=False)  # 체력
    base_stat = Column(Integer, nullable=False)  # 힘민지
    
    options = relationship("ItemOption", back_populates="auction_accessory")
    raw_options = relationship("RawItemOption", back_populates="auction_accessory")

    __table_args__ = (
        Index('idx_acc_status_sold_at', 'status', 'sold_at'),
        Index('idx_acc_end_time_status', 'end_time', 'status')
    )

class ItemOption(Base):
    __tablename__ = 'item_options'
    
    id = Column(Integer, primary_key=True)
    auction_accessory_id = Column(Integer, ForeignKey('auction_accessories.id'), index=True)
    option_name = Column(String, nullable=False, index=True)
    option_grade = Column(Integer, nullable=False)
    
    auction_accessory = relationship("AuctionAccessory", back_populates="options")

    __table_args__ = (
        Index('idx_option_search', 'option_name', 'option_grade'),
    )

class RawItemOption(Base):
    __tablename__ = 'raw_item_options'
    
    id = Column(Integer, primary_key=True)
    auction_accessory_id = Column(Integer, ForeignKey('auction_accessories.id'), index=True)
    option_name = Column(String, nullable=False)
    option_value = Column(Float, nullable=False)
    is_percentage = Column(Boolean, nullable=False)
    
    auction_accessory = relationship("AuctionAccessory", back_populates="raw_options")

class AuctionBracelet(Base):
    __tablename__ = 'auction_bracelets'
    
    id = Column(Integer, primary_key=True)
    grade = Column(String, nullable=False, index=True)  # 고대/유물
    name = Column(String, nullable=False)
    trade_count = Column(Integer, nullable=False)
    price = Column(Integer, nullable=False)
    end_time = Column(DateTime, nullable=False)
    first_seen_at = Column(DateTime, nullable=False, index=True)  # 처음 발견된 시간
    last_seen_at = Column(DateTime, nullable=False, index=True)   # 마지막으로 발견된 시간
    sold_at = Column(DateTime, index=True)  # 판매된 것으로 추정되는 시간
    status = Column(SQLEnum(AuctionStatus), nullable=False, index=True, default=AuctionStatus.ACTIVE)
    fixed_option_count = Column(Integer, nullable=False)  # 1 또는 2
    extra_option_count = Column(Integer, nullable=False)
    
    combat_stats = relationship("BraceletCombatStat", back_populates="auction_bracelet")
    base_stats = relationship("BraceletBaseStat", back_populates="auction_bracelet")
    special_effects = relationship("BraceletSpecialEffect", back_populates="auction_bracelet")

    __table_args__ = (
        Index('idx_bracelet_status_sold_at', 'status', 'sold_at'),
        Index('idx_bracelet_end_time_status', 'end_time', 'status')
    )

class BraceletCombatStat(Base):
    __tablename__ = 'bracelet_combat_stats'
    
    id = Column(Integer, primary_key=True)
    auction_bracelet_id = Column(Integer, ForeignKey('auction_bracelets.id'), index=True)
    stat_type = Column(String, nullable=False)  # 특화/치명/신속
    value = Column(Integer, nullable=False)
    
    auction_bracelet = relationship("AuctionBracelet", back_populates="combat_stats")

    __table_args__ = (
        Index('idx_combat_stat', 'stat_type', 'value'),
    )

class BraceletBaseStat(Base):
    __tablename__ = 'bracelet_base_stats'
    
    id = Column(Integer, primary_key=True)
    auction_bracelet_id = Column(Integer, ForeignKey('auction_bracelets.id'), index=True)
    stat_type = Column(String, nullable=False)  # 힘/민첩/지능
    value = Column(Integer, nullable=False)
    
    auction_bracelet = relationship("AuctionBracelet", back_populates="base_stats")

    __table_args__ = (
        Index('idx_base_stat', 'stat_type', 'value'),
    )

class BraceletSpecialEffect(Base):
    __tablename__ = 'bracelet_special_effects'
    
    id = Column(Integer, primary_key=True)
    auction_bracelet_id = Column(Integer, ForeignKey('auction_bracelets.id'), index=True)
    effect_type = Column(String, nullable=False)
    value = Column(Float, nullable=True)
    
    auction_bracelet = relationship("AuctionBracelet", back_populates="special_effects")

    __table_args__ = (
        Index('idx_special_effect', 'effect_type', 'value'),
    )

class RawDatabaseManager(BaseDatabaseManager):
    def get_database_url(self) -> str:
        return 'sqlite:///lostark_auction.db'
    
    def get_base_metadata(self):
        return Base.metadata

    def _find_identical_accessory(self, session, item) -> Optional[AuctionAccessory]:
        # 아이템에서 end_time 추출
        end_time = datetime.fromisoformat(item["AuctionInfo"]["EndDate"])
        
        candidates = session.query(AuctionAccessory).filter(
            AuctionAccessory.end_time == end_time,
            AuctionAccessory.status.in_([AuctionStatus.ACTIVE, AuctionStatus.SOLD])
        ).all()

        if not candidates:
            return None
        
        if len(candidates) == 1:
            # EndDate로 유일하게 식별됨
            return candidates[0]
        
        # 여러 개 발견된 경우 로그 출력 후 세부 비교
        print(f"⚠️  Multiple items found with same EndDate: {end_time} ({len(candidates)} items)")
        
        # 아이템에서 필요한 정보 추출
        part = "목걸이" if "목걸이" in item["Name"] else ("귀걸이" if "귀걸이" in item["Name"] else "반지")
        
        # 세부 비교
        candidates = [c for c in candidates if (
            c.grade == item["Grade"] and
            c.name == item["Name"] and
            c.part == part and
            c.level == item["AuctionInfo"]["UpgradeLevel"] and
            c.quality == item["GradeQuality"] and
            c.price == item["AuctionInfo"]["BuyPrice"] and
            c.trade_count == item["AuctionInfo"]["TradeAllowCount"]
        )]

        if not candidates:
            return None
        
        if len(candidates) == 1:
            return candidates[0]
        
        # 세부 비교 후에도 여러 개 발견된 경우
        print(f"⚠️  Multiple items after detailed comparison: {len(candidates)} items (Grade: {item['Grade']}, Name: {item['Name']}, Price: {item['AuctionInfo']['BuyPrice']})")
        return candidates[0]  # 첫 번째 후보 반환

    def _find_identical_bracelet(self, session, item) -> Optional[AuctionBracelet]:
        # 아이템에서 end_time 추출
        end_time = datetime.fromisoformat(item["AuctionInfo"]["EndDate"])
        
        candidates = session.query(AuctionBracelet).filter(
            AuctionBracelet.end_time == end_time,
            AuctionBracelet.status.in_([AuctionStatus.ACTIVE, AuctionStatus.SOLD])
        ).all()

        if not candidates:
            return None
        
        if len(candidates) == 1:
            # EndDate로 유일하게 식별됨
            return candidates[0]
        
        # 여러 개 발견된 경우 로그 출력 후 세부 비교
        print(f"⚠️  Multiple bracelets found with same EndDate: {end_time} ({len(candidates)} items)")
        
        # 세부 비교 (grade, name, price, trade_count만)
        candidates = [c for c in candidates if (
            c.grade == item["Grade"] and
            c.name == item["Name"] and
            c.price == item["AuctionInfo"]["BuyPrice"] and
            c.trade_count == item["AuctionInfo"]["TradeAllowCount"]
        )]

        if not candidates:
            return None
        
        if len(candidates) == 1:
            return candidates[0]
        
        # 세부 비교 후에도 여러 개 발견된 경우
        print(f"⚠️  Multiple bracelets after detailed comparison: {len(candidates)} items (Grade: {item['Grade']}, Name: {item['Name']}, Price: {item['AuctionInfo']['BuyPrice']})")
        return candidates[0]  # 첫 번째 후보 반환

    async def bulk_save_accessories(self, raw_items):
        """악세서리 아이템들을 일괄 저장하고 상세 통계 반환"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_bulk_save_accessories, raw_items)

    async def bulk_save_bracelets(self, raw_items):
        """팔찌 아이템들을 일괄 저장하고 상세 통계 반환"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._sync_bulk_save_bracelets, raw_items)

    def _sync_bulk_save_accessories(self, raw_items):
        """악세서리 아이템들을 동기 방식으로 일괄 저장"""

        stats = {
            'total_items': len(raw_items),
            'existing_updated': 0,
            'new_items_added': 0
        }
        
        with self.get_write_session() as session:
            for item, search_timestamp in raw_items:
                # 중복 아이템 찾기
                existing_item = self._find_identical_accessory(session, item)
                
                # 아이템에서 필요한 정보 추출 (새 아이템 생성시 필요)
                part = "목걸이" if "목걸이" in item["Name"] else ("귀걸이" if "귀걸이" in item["Name"] else "반지")
                end_time = datetime.fromisoformat(item["AuctionInfo"]["EndDate"])
                
                if existing_item:
                    # 기존 아이템 업데이트
                    existing_item.last_seen_at = search_timestamp  # type: ignore
                    existing_item.status = AuctionStatus.ACTIVE  # type: ignore
                    stats['existing_updated'] += 1
                else:
                    # 새 아이템 생성
                    record = AuctionAccessory(
                        grade=item["Grade"],
                        name=item["Name"],
                        part=part,
                        level=item["AuctionInfo"]["UpgradeLevel"],
                        quality=item["GradeQuality"],
                        trade_count=item["AuctionInfo"]["TradeAllowCount"],
                        price=item["AuctionInfo"]["BuyPrice"],
                        end_time=end_time,
                        first_seen_at=search_timestamp,
                        last_seen_at=search_timestamp,
                        status=AuctionStatus.ACTIVE,
                        hp=0,
                        base_stat=0
                    )
                    
                    # 옵션명 정규화 및 처리
                    fix_dup_options(item)
                    
                    for option in item["Options"]:
                        option_name = option["OptionName"]
                        opt_value = option["Value"]
                        
                        # 깨달음 제외하고 옵션 데이터 저장 및 체력과 힘민지 값 설정
                        if option_name == "체력":
                            record.hp = int(opt_value)  # type: ignore
                        elif option_name in ["힘", "민첩", "지능"]:
                            record.base_stat = int(opt_value)  # type: ignore
                        elif option_name != "깨달음":
                            # ItemOption 추가
                            opt_grade = number_to_scale.get(option_name, {}).get(opt_value, 1)
                            item_option = ItemOption(
                                option_name=option_name,
                                option_grade=opt_grade
                            )
                            record.options.append(item_option)
                            
                            # RawItemOption 추가
                            raw_option = RawItemOption(
                                option_name=option_name,
                                option_value=opt_value,
                                is_percentage=option.get("IsValuePercentage", False)
                            )
                            record.raw_options.append(raw_option)
                    
                    session.add(record)
                    stats['new_items_added'] += 1
            
            session.flush()
        
        return stats

    def _sync_bulk_save_bracelets(self, raw_items):
        """팔찌 아이템들을 동기 방식으로 일괄 저장"""
        stats = {
            'total_items': len(raw_items),
            'existing_updated': 0,
            'new_items_added': 0
        }
        
        with self.get_write_session() as session:
            for item, search_timestamp in raw_items:
                # 중복 아이템 찾기
                existing_item = self._find_identical_bracelet(session, item)
                
                # 아이템에서 필요한 정보 추출 (새 아이템 생성시 필요)
                end_time = datetime.fromisoformat(item["AuctionInfo"]["EndDate"])
                
                # 옵션 데이터 초기화
                fixed_option_count = len(item["Options"]) - 2  # 부여 효과 수량, 도약 제외
                extra_option_count = 0
                
                if existing_item:
                    # 기존 아이템 업데이트
                    existing_item.last_seen_at = search_timestamp  # type: ignore
                    existing_item.status = AuctionStatus.ACTIVE  # type: ignore
                    stats['existing_updated'] += 1
                else:
                    # 새 아이템 생성
                    record = AuctionBracelet(
                        grade=item["Grade"],
                        name=item["Name"],
                        trade_count=item["AuctionInfo"]["TradeAllowCount"],
                        price=item["AuctionInfo"]["BuyPrice"],
                        end_time=end_time,
                        first_seen_at=search_timestamp,
                        last_seen_at=search_timestamp,
                        status=AuctionStatus.ACTIVE,
                        fixed_option_count=fixed_option_count,
                        extra_option_count=extra_option_count
                    )
                    
                    # 옵션 처리 및 관련 객체 생성
                    for option in item["Options"]:
                        option_type = option["Type"]
                        option_name = option["OptionName"]
                        value = option["Value"]

                        if option_type == "ARK_PASSIVE":
                            continue
                        elif option_type == "BRACELET_RANDOM_SLOT":
                            extra_option_count = value
                            record.extra_option_count = extra_option_count  # type: ignore
                        elif option_type == "STAT" and option_name in ["특화", "치명", "신속", "제압", "인내", "숙련"]:
                            combat_stat = BraceletCombatStat(
                                stat_type=option_name,
                                value=value
                            )
                            record.combat_stats.append(combat_stat)
                        elif option_type == "STAT" and option_name in ["힘", "민첩", "지능"]:
                            base_stat = BraceletBaseStat(
                                stat_type=option_name,
                                value=value
                            )
                            record.base_stats.append(base_stat)
                        else:
                            special_effect = BraceletSpecialEffect(
                                effect_type=option_name,
                                value=value
                            )
                            record.special_effects.append(special_effect)
                    
                    session.add(record)
                    stats['new_items_added'] += 1
            
            session.flush()
        
        return stats


