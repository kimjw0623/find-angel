"""
알림 채널 베이스 클래스
"""
from abc import ABC, abstractmethod
from typing import Optional

class BaseNotificationChannel(ABC):
    """모든 알림 채널의 베이스 클래스"""
    
    def __init__(self, name: str):
        self.name = name
        self.is_enabled = True
    
    @abstractmethod
    async def send_message(self, message) -> Optional[str]:
        """
        메시지 전송
        
        Args:
            message: NotificationMessage 객체
            
        Returns:
            str: 메시지 ID (성공 시), None (실패 시)
        """
        pass
    
    async def update_message(self, message_id: str, new_content: str) -> bool:
        """
        메시지 업데이트 (선택적 구현)
        
        Args:
            message_id: 업데이트할 메시지 ID
            new_content: 새로운 내용
            
        Returns:
            bool: 성공 여부
        """
        return False
    
    async def delete_message(self, message_id: str) -> bool:
        """
        메시지 삭제 (선택적 구현)
        
        Args:
            message_id: 삭제할 메시지 ID
            
        Returns:
            bool: 성공 여부
        """
        return False
    
    async def health_check(self) -> bool:
        """
        채널 상태 확인
        
        Returns:
            bool: 채널이 정상 작동하는지 여부
        """
        return True
    
    async def close(self):
        """리소스 정리"""
        pass
    
    def enable(self):
        """채널 활성화"""
        self.is_enabled = True
    
    def disable(self):
        """채널 비활성화"""
        self.is_enabled = False