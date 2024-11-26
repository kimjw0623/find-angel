# config.py
from typing import List
from dotenv import load_dotenv
import os

class Config:
    def __init__(self):
        load_dotenv()
        
        # 용도별 토큰 로드
        self.price_tokens = self._load_tokens_by_prefix('PRICE_TOKEN_')
        # self.monitor_tokens = self._load_tokens_by_prefix('MONITOR_TOKEN_')
        # self.abidos_tokens = self._load_tokens_by_prefix('ABIDOS_TOKEN_')

    def _load_tokens_by_prefix(self, prefix: str) -> List[str]:
        """특정 프리픽스를 가진 토큰들을 로드"""
        tokens = [value for key, value in os.environ.items() 
                 if key.startswith(prefix)]
        
        if not tokens:
            raise ValueError(f"No tokens found with prefix {prefix}")
            
        return tokens

# 싱글톤 인스턴스 생성
config = Config()