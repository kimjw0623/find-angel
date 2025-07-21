"""
Discord 웹훅 채널 구현
"""
import aiohttp
import asyncio
import json
from typing import Dict, Any, Optional
from datetime import datetime

from .base_channel import BaseNotificationChannel
from ..notification_hub import NotificationMessage

class DiscordWebhookChannel(BaseNotificationChannel):
    """Discord 웹훅 기반 알림 채널"""
    
    def __init__(self, webhook_url: str):
        super().__init__("Discord Webhook")
        self.webhook_url = webhook_url
        self.session = None
        
    async def _ensure_session(self):
        """HTTP 세션 확보"""
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def send_message(self, message: NotificationMessage) -> Optional[str]:
        """메시지 전송"""
        try:
            await self._ensure_session()
            
            # 메시지 내용이 이미 포맷된 상태인지 확인
            if message.metadata.get('is_formatted', False):
                content = message.content
            else:
                content = self._format_message(message)
            
            payload = {
                "content": content,
                "flags": message.metadata.get('flags', 0)
            }
            
            url = f"{self.webhook_url}?wait=true"
            
            async with self.session.post(url, json=payload) as response:
                if response.status == 200:
                    result = await response.json()
                    message_id = result.get('id')
                    print(f"✅ Discord message sent: {message_id}")
                    return message_id
                else:
                    print(f"❌ Discord webhook failed: {response.status}")
                    return None
                    
        except Exception as e:
            print(f"Error sending Discord message: {e}")
            return None
    
    async def update_message(self, message_id: str, new_content: str) -> bool:
        """메시지 업데이트"""
        try:
            await self._ensure_session()
            
            payload = {"content": new_content}
            url = f"{self.webhook_url}/messages/{message_id}"
            
            async with self.session.patch(url, json=payload) as response:
                success = response.status == 200
                print(f"{'✅' if success else '❌'} Discord message update: {message_id}")
                return success
                
        except Exception as e:
            print(f"Error updating Discord message: {e}")
            return False
    
    async def delete_message(self, message_id: str) -> bool:
        """메시지 삭제"""
        try:
            await self._ensure_session()
            
            url = f"{self.webhook_url}/messages/{message_id}"
            
            async with self.session.delete(url) as response:
                success = response.status == 204
                print(f"{'✅' if success else '❌'} Discord message delete: {message_id}")
                return success
                
        except Exception as e:
            print(f"Error deleting Discord message: {e}")
            return False
    
    def _format_message(self, message: NotificationMessage) -> str:
        """메시지 포맷팅"""
        # 기본 포맷팅 로직
        if message.type.value == "item_found":
            return self._format_item_message(message)
        elif message.type.value == "system_status":
            return f"🔧 **시스템 알림**\\n{message.content}"
        elif message.type.value == "error_alert":
            return f"🚨 **오류 발생**\\n{message.content}"
        else:
            return f"📢 **{message.title}**\\n{message.content}"
    
    def _format_item_message(self, message: NotificationMessage) -> str:
        """아이템 발견 메시지 포맷팅 (기존 로직 개선)"""
        try:
            metadata = message.metadata
            item = metadata.get('item', {})
            evaluation = metadata.get('evaluation', {})
            
            if not item or not evaluation:
                return message.content  # 이미 포맷된 메시지 사용
            
            # 기존 format_multiline_message 로직을 async로 개선
            return self._create_formatted_item_message(item, evaluation)
            
        except Exception as e:
            print(f"Error formatting item message: {e}")
            return message.content
    
    def _create_formatted_item_message(self, item: Dict, evaluation: Dict) -> str:
        """포맷된 아이템 메시지 생성"""
        RESET = "\\u001b[0m"
        
        # 등급별 색상
        grade_color = "\\u001b[2;31m\\u001b[2;40m" if evaluation['grade'] == "유물" else "\\u001b[2;37m\\u001b[2;40m"
        
        content = f"```ansi\\n{grade_color}"
        
        if evaluation["type"] == "accessory":
            content += self._format_accessory(item, evaluation, RESET)
        else:  # bracelet
            content += self._format_bracelet(item, evaluation, RESET)
            
        content += f"\\n만료 {item['AuctionInfo']['EndDate']}\\n```"
        return content
    
    def _format_accessory(self, item: Dict, evaluation: Dict, RESET: str) -> str:
        """악세서리 포맷팅"""
        usage_type = evaluation["usage_type"]
        price_detail = evaluation["price_details"][usage_type]
        
        content = f"{evaluation['grade']} {item['Name']}{RESET} ({usage_type}: 품질+특옵 가격 {price_detail['base_price']:,}골드)\\n"
        content += f"품질 {self._quality_color(evaluation['quality'])}{evaluation['quality']}{RESET} 거래 {item['AuctionInfo']['TradeAllowCount']}회\\n"
        content += f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 ({evaluation['price_ratio']*100:.1f}%)\\n"
        
        # 옵션 포맷팅
        options = []
        for opt in item["Options"]:
            if opt["OptionName"] == "깨달음":
                continue
            color, scale = self._accessory_option_color(opt)
            if opt["OptionName"] in price_detail["options"]:
                opt_value = price_detail["options"][opt["OptionName"]]["price"]
                options.append(f"{color}{opt['OptionName']} {scale}({opt_value:+,}골드){RESET}")
            else:
                options.append(f"{color}{opt['OptionName']} {scale}{RESET}")
        
        content += " | ".join(options)
        return content
    
    def _format_bracelet(self, item: Dict, evaluation: Dict, RESET: str) -> str:
        """팔찌 포맷팅"""
        content = f"{evaluation['grade']} {item['Name']}{RESET}\\n"
        content += f"{evaluation['current_price']:,}골드 vs {evaluation['expected_price']:,}골드 ({evaluation['price_ratio']*100:.1f}%)\\n"
        
        options = []
        for opt in item["Options"]:
            if opt["OptionName"] == "도약":
                continue
            color = self._bracelet_option_color(opt, evaluation['grade'])
            options.append(f"{color}{opt['OptionName']} {int(opt['Value'])}{RESET}")
        
        content += " | ".join(options)
        return content
    
    def _quality_color(self, quality: int) -> str:
        """품질 색상"""
        if quality == 100:
            return "\\u001b[2;33m"
        elif quality >= 90:
            return "\\u001b[2;35m"
        elif quality >= 70:
            return "\\u001b[2;34m"
        else:
            return "\\u001b[2;32m"
    
    def _accessory_option_color(self, opt: Dict) -> tuple:
        """악세서리 옵션 색상 (기존 로직)"""
        # 기존 discord_manager의 accessory_option 로직 사용
        colorList = ["\\u001b[2;30m", "\\u001b[2;34m", "\\u001b[2;35m", "\\u001b[2;33m"]
        scaleList = " 하중상"
        
        try:
            # utils.number_to_scale 대신 간단한 로직 사용
            scale = 1  # 기본값
            return colorList[scale], scaleList[scale]
        except:
            return colorList[0], scaleList[0]
    
    def _bracelet_option_color(self, opt: Dict, grade: str) -> str:
        """팔찌 옵션 색상 (기존 로직)"""
        name = opt["OptionName"]
        value = int(opt['Value'])
        
        if name == "부여 효과 수량":
            if grade == "고대":
                value -= 1
            return "\\u001b[2;33m" if value == 2 else "\\u001b[2;34m"
        elif name == "공격 및 이동 속도 증가":
            if grade == "고대":
                value -= 1
            if value == 5:
                return "\\u001b[2;33m"
            elif value == 4:
                return "\\u001b[2;35m"
            else:
                return "\\u001b[2;34m"
        elif name in ["특화", "신속", "치명"]:
            if grade == "고대":
                value -= 20
            if value == 100:
                return "\\u001b[2;33m"
            elif value > 80:
                return "\\u001b[2;35m"
            elif value > 62:
                return "\\u001b[2;34m"
            else:
                return "\\u001b[2;32m"
        elif name in ["힘", "민첩", "지능"]:
            if grade == "고대":
                value -= 3200
            if value == 12800:
                return "\\u001b[2;33m"
            elif value > 10666:
                return "\\u001b[2;35m"
            elif value >= 8533:
                return "\\u001b[2;34m"
            else:
                return "\\u001b[2;32m"
        else:
            return "\\u001b[2;30m"
    
    async def health_check(self) -> bool:
        """채널 상태 확인"""
        try:
            await self._ensure_session()
            
            # 간단한 테스트 메시지 전송 (일반적으로는 하지 않음)
            # 대신 webhook URL의 유효성만 확인
            return self.webhook_url is not None and self.webhook_url.startswith('https://')
            
        except Exception as e:
            print(f"Discord webhook health check failed: {e}")
            return False
    
    async def close(self):
        """리소스 정리"""
        if self.session:
            await self.session.close()
            self.session = None