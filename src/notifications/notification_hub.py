"""
통합 알림 허브 - Discord, 봇, 기타 채널을 관리하는 중앙 서비스
"""
import asyncio
import json
import time
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

from src.common.ipc_utils import IPCServer, MessageTypes

class NotificationType(Enum):
    ITEM_FOUND = "item_found"
    SYSTEM_STATUS = "system_status"
    ERROR_ALERT = "error_alert"

class ChannelType(Enum):
    DISCORD_WEBHOOK = "discord_webhook"
    DISCORD_BOT = "discord_bot"
    TELEGRAM = "telegram"
    SLACK = "slack"

@dataclass
class NotificationMessage:
    type: NotificationType
    title: str
    content: str
    priority: int = 1  # 1=낮음, 2=중간, 3=높음
    channels: List[ChannelType] = None
    metadata: Dict[str, Any] = None
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.channels is None:
            self.channels = [ChannelType.DISCORD_WEBHOOK]
        if self.timestamp is None:
            self.timestamp = datetime.now()
        if self.metadata is None:
            self.metadata = {}

class NotificationHub:
    """중앙 알림 관리 서비스"""
    
    def __init__(self):
        self.is_running = False
        self.notification_queue = asyncio.Queue()
        self.channels = {}
        self.tracking_items = {}  # 추적 중인 아이템들
        
        # IPC 서버 설정
        self.ipc_server = IPCServer("/tmp/find_angel_notifications.sock")
        self.ipc_server.register_handler(
            MessageTypes.ITEM_FOUND, 
            self._handle_item_notification
        )
        
        # 채널 초기화
        self._initialize_channels()
        
    def _initialize_channels(self):
        """알림 채널들 초기화"""
        from .channels.discord_webhook import DiscordWebhookChannel
        from .channels.discord_bot import DiscordBotChannel
        
        # Discord 웹훅 채널
        webhook_url = os.getenv("WEBHOOK2")
        if webhook_url:
            self.channels[ChannelType.DISCORD_WEBHOOK] = DiscordWebhookChannel(webhook_url)
            
        # Discord 봇 채널 (향후 구현)
        bot_token = os.getenv("DISCORD_BOT_TOKEN")
        if bot_token:
            self.channels[ChannelType.DISCORD_BOT] = DiscordBotChannel(bot_token)
    
    async def start(self):
        """알림 허브 시작"""
        print("🔔 Starting Notification Hub...")
        self.is_running = True
        
        # IPC 서버 시작
        self.ipc_server.start_server()
        
        # 작업들을 병렬로 실행
        await asyncio.gather(
            self._notification_processor(),
            self._item_tracker(),
            self._health_monitor()
        )
    
    async def _notification_processor(self):
        """알림 메시지 처리기"""
        while self.is_running:
            try:
                message = await self.notification_queue.get()
                await self._process_notification(message)
                self.notification_queue.task_done()
            except Exception as e:
                print(f"Error processing notification: {e}")
                await asyncio.sleep(1)
    
    async def _process_notification(self, message: NotificationMessage):
        """개별 알림 메시지 처리"""
        print(f"📬 Processing notification: {message.title}")
        
        # 각 채널로 병렬 전송
        tasks = []
        for channel_type in message.channels:
            if channel_type in self.channels:
                channel = self.channels[channel_type]
                tasks.append(channel.send_message(message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def _item_tracker(self):
        """아이템 추적 및 상태 업데이트"""
        while self.is_running:
            try:
                current_time = time.time()
                expired_items = []
                
                for item_id, tracking_info in self.tracking_items.items():
                    # 10분 경과한 아이템은 추적 종료
                    if current_time - tracking_info['start_time'] > 600:
                        expired_items.append(item_id)
                        await self._update_item_status(tracking_info, "추적 종료")
                    else:
                        # 아이템 존재 여부 확인
                        if await self._check_item_existence(tracking_info):
                            continue  # 아직 존재함
                        else:
                            expired_items.append(item_id)
                            await self._update_item_status(tracking_info, "판매 완료")
                
                # 만료된 아이템들 제거
                for item_id in expired_items:
                    del self.tracking_items[item_id]
                    
            except Exception as e:
                print(f"Error in item tracker: {e}")
            
            await asyncio.sleep(30)  # 30초마다 체크
    
    async def _health_monitor(self):
        """서비스 상태 모니터링"""
        while self.is_running:
            try:
                # 채널 상태 체크
                for channel_type, channel in self.channels.items():
                    if hasattr(channel, 'health_check'):
                        healthy = await channel.health_check()
                        if not healthy:
                            print(f"⚠️ Channel {channel_type} health check failed")
                            
            except Exception as e:
                print(f"Error in health monitor: {e}")
            
            await asyncio.sleep(300)  # 5분마다 체크
    
    def _handle_item_notification(self, message):
        """IPC로 받은 아이템 알림 처리"""
        try:
            data = message['data']
            
            # 알림 메시지 생성
            notification = NotificationMessage(
                type=NotificationType.ITEM_FOUND,
                title=f"유망 매물 발견: {data['item_name']}",
                content=data['formatted_message'],
                priority=2,
                metadata=data
            )
            
            # 큐에 추가 (비동기적으로 처리됨)
            asyncio.create_task(self.notification_queue.put(notification))
            
            # 추적 시작
            if data.get('track_item', True):
                item_id = data.get('item_id', f"{data['item_name']}_{time.time()}")
                self.tracking_items[item_id] = {
                    'item': data['item'],
                    'evaluation': data['evaluation'],
                    'message_id': None,  # 채널에서 설정
                    'start_time': time.time()
                }
            
            return {'status': 'queued', 'timestamp': datetime.now().isoformat()}
            
        except Exception as e:
            print(f"Error handling item notification: {e}")
            return {'status': 'error', 'message': str(e)}
    
    async def _check_item_existence(self, tracking_info):
        """아이템이 여전히 경매장에 있는지 확인"""
        # 기존 check_existance 로직을 async로 개선
        try:
            from ..core.item_checker_utils import check_item_existence
            return await check_item_existence(
                tracking_info['item'], 
                tracking_info['evaluation']
            )
        except Exception as e:
            print(f"Error checking item existence: {e}")
            return False
    
    async def _update_item_status(self, tracking_info, status):
        """아이템 상태 업데이트 (메시지 수정)"""
        try:
            if tracking_info.get('message_id'):
                # Discord 메시지 업데이트
                webhook_channel = self.channels.get(ChannelType.DISCORD_WEBHOOK)
                if webhook_channel:
                    await webhook_channel.update_message(
                        tracking_info['message_id'],
                        status
                    )
        except Exception as e:
            print(f"Error updating item status: {e}")
    
    def stop(self):
        """서비스 중지"""
        print("🔔 Stopping Notification Hub...")
        self.is_running = False
        self.ipc_server.stop_server()

# 전역 클라이언트 함수들
def send_item_notification(item: Dict, evaluation: Dict, formatted_message: str):
    """아이템 발견 알림 전송"""
    from src.common.ipc_utils import get_ipc_client
    
    client = get_ipc_client()
    client.socket_path = "/tmp/find_angel_notifications.sock"
    
    return client.send_message(
        "item_found",
        {
            'item': item,
            'evaluation': evaluation,
            'formatted_message': formatted_message,
            'item_name': item.get('Name', 'Unknown'),
            'item_id': f"{item.get('Name', 'Unknown')}_{time.time()}"
        }
    )

# 메인 실행부
async def main():
    hub = NotificationHub()
    try:
        await hub.start()
    except KeyboardInterrupt:
        hub.stop()

if __name__ == "__main__":
    asyncio.run(main())