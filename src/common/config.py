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
        
        # 캐시 업데이트 설정
        self.cache_update_interval_hours = 24
        self.search_cycle_delay_seconds = 2
        
        # 가격 평가 설정
        self.price_evaluation = {
            "min_expected_value": 20000,  # 최소 기댓값 (골드)
            "sigmoid_params": {
                "x0": 0.625,  # sigmoid 중심점
                "k": 10       # sigmoid 가파름 정도
            },
            "quality_thresholds": {
                "ancient": [70, 80, 90, 95, 98, 100],
                "relic": [30, 50, 70, 80, 90, 100]
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
            "tracking_duration_seconds": 600
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
            "combat_stat_search_values": [40, 50, 60, 70, 80, 90],
            "base_stat_search_values": [6400, 8000, 9600, 11200],
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
        
        # API 검색 설정
        self.api_search_settings = {
            "item_level_min": 0,
            "item_level_max": 1800,
            "item_tier": 4,
            "max_pages_per_search": 1000
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