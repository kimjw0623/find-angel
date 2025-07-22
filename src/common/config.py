# config.py
from typing import List, Dict
from dotenv import load_dotenv
import os

class Config:
    def __init__(self):
        load_dotenv()
        
        # 용도별 토큰 로드
        self.price_tokens = self._load_tokens_by_prefix('PRICE_TOKEN_')
        self.monitor_tokens = self._load_tokens_by_prefix('MONITOR_TOKEN_')
        # self.abidos_tokens = self._load_tokens_by_prefix('ABIDOS_TOKEN_')
        
        # 웹훅 URL 로드
        self.webhook_urls = self._load_webhooks()
        
        # API 설정
        self.api_base_url = "https://developer-lostark.game.onstove.com"
        self.api_auction_endpoint = "/auctions/items"
        
        # 페이징 설정
        self.items_per_page = 10
        self.max_pages_per_search = 1000
        
        self.search_cycle_delay_seconds = 2
        
        # 가격 평가 설정
        self.price_evaluation = {
            "min_expected_value": 20000,  # 최소 기댓값 (골드)
            "sigmoid_params": {
                "x0": 0.625,  # sigmoid 중심점
                "k": 10       # sigmoid 가파름 정도
            }
        }
        
        # 아이템 검색 설정
        self.search_settings = {
            "retry_delay_seconds": 3,
            "max_retries": 6,
            "batch_size": 50,
            "rate_limit_per_minute": 100
        }
        
        # 품질 설정
        self.quality_settings = {
            "min_quality_threshold": 67,
            "quality_rounding": 10,
            "quality_search_values": [60, 70, 80, 90],
            "quality_color_thresholds": {
                "legendary": 100,
                "epic": 90,
                "rare": 70
            }
        }
        
        # 연마 설정
        self.enhancement_settings = {
            "levels": [0, 1, 2, 3],
            "max_level": 3
        }
        
        # 배치 처리 설정
        self.batch_settings = {
            "three_day_batch_size": 5,
            "one_day_batch_size": 10,
            "initial_one_day_page": 500
        }
        
        # 시간 설정
        self.time_settings = {
            "safety_buffer_seconds": 2,
            "error_retry_delay": 60,
            "scan_interval": 1,
            "cache_check_interval": 60,
            "three_day_buffer_minutes": 3,
            "one_day_buffer_minutes": 1,
            "tracking_duration_seconds": 600,
            "price_collection_interval_minutes": 2  # 가격 수집 간격 (분)
        }
        
        # 가격 평가 추가 설정
        self.price_evaluation.update({
            "min_price": 1,
            "bracelet_warning_threshold": 5000,
            "sigmoid_min_ratio": 0.5,
            "sigmoid_max_ratio": 0.75,
            "sigmoid_max_price": 400000,
            "sigmoid_k": 3e-5
        })
        
        # 팔찌 설정
        self.bracelet_settings = {
            "ancient_slot_bonus": 1,
            "ancient_combat_stat_bonus": 20,
            "ancient_base_stat_bonus": 3200,
            "combat_stat_thresholds": [40, 50, 60, 70, 80, 90],  # 전투 특성 구간
            "base_stat_thresholds": [6400, 8000, 9600, 11200],   # 기본 스탯 구간
            "stat_thresholds": {
                "combat_stats": {
                    "legendary": 100,
                    "epic": 80,
                    "rare": 62,
                    "common": 40
                },
                "base_stats": {
                    "legendary": 12800,
                    "epic": 10666,
                    "rare": 8533,
                    "common": 6400
                }
            }
        }
              
        # 아이템 체커 설정
        self.item_checker_settings = {
            "scan_interval_seconds": 1,           # 스캔 주기
            "batch_size_3day": 5,                 # 3일 매물 배치 크기
            "batch_size_1day": 10,                # 1일 매물 배치 크기
            "start_page_1day": 500,               # 1일 매물 시작 페이지
            "search_params": {
                "ItemLevelMin": 0,
                "ItemLevelMax": 1800,
                "ItemTier": 4,
                "CategoryCode": 200000,
                "Sort": "EXPIREDATE",
                "SortCondition": "DESC"
            },
            "time_offsets": {
                "expire_3day_offset_minutes": 3,  # 3일 매물 시간 오프셋
                "expire_1day_offset_minutes": 1   # 1일 매물 시간 오프셋
            }
        }
        
        # Discord 설정
        self.discord_settings = {
            "ephemeral_flag": 1 << 12,
            "color_codes": {
                "gray": "\\u001b[2;30m",
                "blue": "\\u001b[2;34m",
                "purple": "\\u001b[2;35m",
                "yellow": "\\u001b[2;33m",
                "green": "\\u001b[2;32m",
                "red": "\\u001b[2;31m",
                "white": "\\u001b[2;37m",
                "black_bg": "\\u001b[2;40m"
            }
        }
        
        # 악세서리 base_stat 범위 설정
        # 부위별, 연마 레벨별 최소-최대 base_stat 값
        self.accessory_base_stat_ranges = {
            "반지": {
                0: (9156, 11091),
                1: (9414, 11349), 
                2: (9930, 11865),
                3: (10962, 12897)
            },
            "귀걸이": {
                0: (9861, 11944),
                1: (10139, 12222),
                2: (10695, 12778), 
                3: (11806, 13889)
            },
            "목걸이": {
                0: (12678, 15357),
                1: (13035, 15714),
                2: (13749, 16428),
                3: (15178, 17856)
            }
        }
        
        # base_stat 비율 계산 설정
        self.base_stat_ratio_settings = {
            "model_type": "linear",  # 추후 "quadratic", "exponential" 등으로 변경 가능
        }
        
        # Pattern Generator 설정
        self.pattern_generator_settings = {
            "min_regression_samples": 10,  # Linear regression 최소 샘플 수
            "min_common_option_samples": 10,  # Common option 분석 최소 샘플 수
            "min_r_squared_threshold": 0.5,  # R-squared 최소 임계값 (이하는 최저가 모델 사용)
            "min_feature_correlation": 0.1,  # 피처별 최소 상관계수 (이하는 피처 제외)
            "success_rate_window_days": 30,  # 판매 성공률 계산 기간 (일)
        }
        
        # 역할별 전용 옵션 설정 (Exclusive Options)
        self.exclusive_options = {
            "목걸이": {
                "dealer": ["추피", "적주피"],
                "support": ["아덴게이지", "낙인력"]
            },
            "귀걸이": {
                "dealer": ["공퍼", "무공퍼"],
                "support": ["무공퍼"]
            },
            "반지": {
                "dealer": ["치적", "치피"],
                "support": ["아공강", "아피강"]
            }
        }
        
        # Common Options 설정 (각 옵션의 값 범위)
        self.common_options = {
            "깡공": [80, 195, 390],
            "깡무공": [195, 480, 960],
            "최생": [1300, 3250, 6500],
            "최마": [6, 15, 30],
            "아군회복": [0.95, 2.1, 3.5],
            "아군보호막": [0.95, 2.1, 3.5]
        }
        
        # 역할별 관련 옵션 매핑 (Common Options 분석용)
        self.role_related_options = {
            "dealer": ["힘민지", "깡공", "깡무공"],
            "support": ["힘민지", "깡무공", "최생", "최마", "아군회복", "아군보호막"]
        }
        
        # 게임 데이터 상수들 (인라인으로 정의)
        
        # 옵션값 → 스케일 매핑 (하/중/상옵)
        self.number_to_scale = {
            "공퍼": {0.4: 1, 0.95: 2, 1.55: 3},
            "깡공": {80.0: 1, 195.0: 2, 390.0: 3},
            "무공퍼": {0.8: 1, 1.8: 2, 3.0: 3},
            "깡무공": {195.0: 1, 480.0: 2, 960.0: 3},
            "치적": {0.4: 1, 0.95: 2, 1.55: 3},
            "치피": {1.1: 1, 2.4: 2, 4.0: 3},
            "추피": {0.7: 1, 1.6: 2, 2.6: 3},
            "적주피": {0.55: 1, 1.2: 2, 2.0: 3},
            "아덴게이지": {1.6: 1, 3.6: 2, 6.0: 3},
            "낙인력": {2.15: 1, 4.8: 2, 8.0: 3},
            "아군회복": {0.95: 1, 2.1: 2, 3.5: 3},
            "아군보호막": {0.95: 1, 2.1: 2, 3.5: 3},
            "아공강": {1.35: 1, 3.0: 2, 5.0: 3},
            "아피강": {2.0: 1, 4.5: 2, 7.5: 3},
            "최마": {6.0: 1, 15.0: 2, 30.0: 3},
            "최생": {1300.0: 1, 3250.0: 2, 6500.0: 3},
            "상태이상공격지속시간": {0.2: 1, 0.5: 2, 1.0: 3},
            "전투중생회": {10.0: 1, 25.0: 2, 50.0: 3},
        }
        
        # 옵션명 약어 ↔ 풀네임 변환
        self.ABB_TO_FULLNAME = {
            "추피": "추가 피해",
            "적주피": "적에게 주는 피해 증가",
            "아덴게이지": "세레나데, 신성, 조화 게이지 획득량 증가",
            "낙인력": "낙인력",
            "아군회복": "파티원 회복 효과",
            "아군보호막": "파티원 보호막 효과",
            "치적": "치명타 적중률",
            "치피": "치명타 피해",
            "아공강": "아군 공격력 강화 효과",
            "아피강": "아군 피해량 강화 효과",
            "최생": "최대 생명력",
            "최마": "최대 마나",
            "상태이상공격지속시간": "상태이상 공격 지속시간",
            "전투중생회": "전투 중 생명력 회복량"
        }
        self.FULLNAME_TO_ABB = {value: key for key, value in self.ABB_TO_FULLNAME.items()}
        
        # API 카테고리 코드
        self.CATEGORY_CODES = {
            "목걸이": 200010,
            "귀걸이": 200020,
            "반지": 200030,
            "팔찌": 200040
        }
        
        # API 검색 옵션 코드
        self.SEARCH_OPTION_CODES = {
            "팔찌 옵션 수량": 4,
            "고정 효과 수량": 1,
            "부여 효과 수량": 2
        }
        
        # 옵션별 API 코드
        self.option_dict = {
            "추피": 41, "적주피": 42, "아덴게이지": 43, "낙인력": 44,
            "공퍼": 45, "무공퍼": 46, "아군회복": 47, "아군보호막": 48,
            "치적": 49, "치피": 50, "아공강": 51, "아피강": 52,
            "깡공": 53, "깡무공": 54, "최생": 55, "최마": 56,
            "상태이상공격지속시간": 57, "전투중생회": 58,
        }
        
        # 팔찌 옵션 코드 매핑
        self.option_dict_bracelet_first = {
            "팔찌 기본 효과": 1, "전투 특성": 2,
            "팔찌 옵션 수량": 4, "팔찌 특수 효과": 5,
        }
        
        self.option_dict_bracelet_second = {
            "고정 효과 수량": 1, "부여 효과 수량": 2,
            "힘": 3, "민첩": 4, "지능": 5, "체력": 6,
            "치명": 15, "특화": 16, "제압": 17, "신속": 18, "인내": 19, "숙련": 20,
            "강타": 39, "공격 및 이동 속도 증가": 60, "긴급 수혈": 33, "돌진": 38,
            "마나회수": 36, "마법 방어력": 2, "멸시": 29, "무시": 30, "물리 방어력": 1,
            "반격": 28, "반전": 31, "속공": 26, "시드 이하 받는 피해 감소": 62,
            "시드 이하 주는 피해 증가": 61, "앵콜": 35, "오뚝이": 37, "응급 처치": 34,
            "이동기 및 기상기 재사용 대기시간 감소": 63, "전투 자원 회복량": 59,
            "전투 중 생명력 회복량": 6, "최대 마나": 4, "최대 생명력": 3,
            "타격": 40, "투자": 27, "피격 이상 면역 효과": 64, "회생": 32,
        }
        
        # 딜증 계산 데이터
        self.dmg_increment_dict = {
            "추피": {"0.7": 0.495, "1.6": 1.131, "2.6": 1.839},
            "적주피": {"0.55": 0.55, "1.2": 1.2, "2.0": 2.0},
            "공퍼": {"0.4": 0.358, "0.95": 0.850, "1.55": 1.387},
            "무공퍼": {"0.8": 0.306, "1.8": 0.686, "3.0": 1.14},
            "치피": {"1.1": 0.365, "2.4": 0.797, "4.0": 1.328},
            "치적": {"0.4": 0.273, "0.95": 0.648, "1.55": 1.057},
            "깡공": {"80.0": 0.059, "195.0": 0.144, "390.0": 0.288},
            "깡무공": {"195.0": 0.061, "480.0": 0.151, "960.0": 0.302},
            "품질": {"목걸이": 0.00785*0.5, "귀걸이": 0.00610*0.5, "반지": 0.00567*0.5}
        }

    def _load_tokens_by_prefix(self, prefix: str) -> List[str]:
        """특정 프리픽스를 가진 토큰들을 로드"""
        tokens = [value for key, value in os.environ.items() 
                 if key.startswith(prefix)]
        
        if not tokens:
            raise ValueError(f"No tokens found with prefix {prefix}")
            
        return tokens
    
    def _load_webhooks(self) -> Dict[str, str]:
        """Discord 웹훅 URL들을 로드"""
        webhooks = {}
        for key, value in os.environ.items():
            if key.startswith('WEBHOOK'):
                # WEBHOOK1 -> webhook1, WEBHOOK -> webhook
                webhook_name = key.lower()
                webhooks[webhook_name] = value
        return webhooks

# 싱글톤 인스턴스 생성
config = Config()