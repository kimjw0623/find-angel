"""공통 타입 정의"""
from typing import Dict, List, Tuple, Optional, TypedDict, Literal, Union
from datetime import datetime

# 기본 타입 별칭
OptionName = str
OptionValue = float
QualityThreshold = int
Price = int
SampleCount = int

# 옵션 관련 타입
OptionTuple = Tuple[OptionName, OptionValue]
OptionList = List[OptionTuple]

# 딜러/서포터 역할
Role = Literal["dealer", "support"]

# 패턴 키 타입
PatternKey = str  # "고대:목걸이:0:[(추피, 0.7)]" 형식

# 품질별 가격 정보
QualityPrices = Dict[QualityThreshold, Price]

# 공통 옵션 가치 정보
CommonOptionValues = Dict[OptionName, Dict[OptionValue, Price]]

# 악세서리 패턴 데이터
class AccessoryPatternData(TypedDict):
    quality_prices: QualityPrices
    common_option_values: CommonOptionValues
    total_sample_count: SampleCount
    last_update: str  # search_cycle_id

# 팔찌 패턴 타입
BraceletPatternType = Literal[
    "전특2", 
    "전특1+기본", 
    "전특1+공이속", 
    "기본+공이속", 
    "전특1+잡옵", 
    "전특1"
]

# 팔찌 패턴 키 (combat_stats, base_stats, extra_slots)
BraceletPatternKey = Tuple[str, str, str]

# 팔찌 가격 정보 (price, sample_count)
BraceletPriceInfo = Tuple[Price, SampleCount]

# 팔찌 패턴 데이터
BraceletPatternData = Dict[BraceletPatternType, Dict[BraceletPatternKey, BraceletPriceInfo]]

# 메모리 패턴 전체 구조
class MemoryPatterns(TypedDict):
    dealer: Dict[PatternKey, AccessoryPatternData]
    support: Dict[PatternKey, AccessoryPatternData]
    bracelet_고대: BraceletPatternData
    bracelet_유물: BraceletPatternData

# 옵션 분류
class OptionCategories(TypedDict):
    dealer_exclusive: OptionList
    support_exclusive: OptionList
    common: OptionList

# 팔찌 패턴 상세 정보
class BraceletPatternDetails(TypedDict):
    pattern: str  # "치명+신속" 등
    values: str   # "70+60" 등
    extra_slots: str  # "부여3" 등

# API 응답 아이템 구조
class AuctionItemData(TypedDict):
    Grade: str
    Name: str
    Part: str  # 악세서리만
    Level: int  # 악세서리만
    Quality: int  # 악세서리만
    AuctionInfo: Dict[str, Union[int, str, bool]]
    Options: List[Dict[str, Union[str, float, bool]]]

# 팔찌 아이템 데이터
class BraceletItemData(TypedDict):
    grade: str
    fixed_option_count: int
    extra_option_count: int
    combat_stats: List[Tuple[str, float]]
    base_stats: List[Tuple[str, float]]
    special_effects: List[Tuple[str, float]]