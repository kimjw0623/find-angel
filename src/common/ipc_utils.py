"""
프로세스 간 통신을 위한 Unix 소켓 유틸리티
"""
import socket
import json
import threading
import time
import os
from datetime import datetime
from typing import Dict, Any, Callable, Optional
from contextlib import contextmanager

class IPCServer:
    """Unix 소켓 기반 IPC 서버"""
    
    def __init__(self, service_name: str = "default", socket_path: str = None):
        if socket_path is None:
            self.socket_path = f"/tmp/find_angel_{service_name}_ipc.sock"
        else:
            self.socket_path = socket_path
        self.service_name = service_name
        self.server_socket = None
        self.is_running = False
        self.message_handlers: Dict[str, Callable] = {}
        
    def register_handler(self, message_type: str, handler: Callable):
        """메시지 타입별 핸들러 등록"""
        self.message_handlers[message_type] = handler
        
    def start_server(self):
        """서버 시작 (별도 스레드에서 실행)"""
        def server_loop():
            # 기존 소켓 파일 제거
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)
                
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(5)
            self.is_running = True
            
            print(f"🔌 IPC Server started at {self.socket_path}")
            
            while self.is_running:
                try:
                    client_socket, _ = self.server_socket.accept()
                    threading.Thread(
                        target=self._handle_client,
                        args=(client_socket,),
                        daemon=True
                    ).start()
                except Exception as e:
                    if self.is_running:  # 정상 종료가 아닌 경우만 에러 출력
                        print(f"IPC Server error: {e}")
                        
        threading.Thread(target=server_loop, daemon=True).start()
        
    def _handle_client(self, client_socket):
        """클라이언트 요청 처리"""
        try:
            data = client_socket.recv(4096).decode('utf-8')
            if data:
                message = json.loads(data)
                message_type = message.get('type')
                
                if message_type in self.message_handlers:
                    response = self.message_handlers[message_type](message)
                    if response:
                        client_socket.send(json.dumps(response).encode('utf-8'))
                        
        except BrokenPipeError:
            # 클라이언트가 응답을 기다리지 않고 연결을 끊은 경우 (정상 상황)
            pass
        except Exception as e:
            print(f"Error handling IPC client: {e}")
        finally:
            client_socket.close()
            
    def stop_server(self):
        """서버 중지"""
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

class IPCClient:
    """Unix 소켓 기반 IPC 클라이언트"""
    
    def __init__(self, target_service: str = "pattern_generator", socket_path: str = None):
        if socket_path is None:
            self.socket_path = f"/tmp/find_angel_{target_service}_ipc.sock"
        else:
            self.socket_path = socket_path
        self.target_service = target_service
        
    def send_message(self, message_type: str, data: Dict[str, Any] = None, timeout: float = 1.0) -> Optional[Dict]:
        """메시지 전송 (응답 대기)"""
        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.settimeout(timeout)
            client_socket.connect(self.socket_path)
            
            message = {
                'type': message_type,
                'timestamp': datetime.now().isoformat(),
                'data': data or {}
            }
            
            client_socket.send(json.dumps(message).encode('utf-8'))
            
            # 응답 대기 (선택적)
            try:
                response_data = client_socket.recv(4096).decode('utf-8')
                if response_data:
                    return json.loads(response_data)
            except socket.timeout:
                pass  # 응답이 없어도 괜찮음
                
            return {'status': 'sent'}
            
        except Exception as e:
            # 연결 실패는 정상적인 상황 (다른 프로세스가 아직 시작 안됨)
            return None
        finally:
            try:
                client_socket.close()
            except:
                pass

    def send_notification(self, message_type: str, data: Dict[str, Any] = None, timeout: float = 0.5) -> bool:
        """일방향 통지 전송 (응답 대기 안함)"""
        try:
            client_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client_socket.settimeout(timeout)
            client_socket.connect(self.socket_path)
            
            message = {
                'type': message_type,
                'timestamp': datetime.now().isoformat(),
                'data': data or {}
            }
            
            client_socket.send(json.dumps(message).encode('utf-8'))
            
            # 즉시 연결 종료 (응답 대기하지 않음)
            client_socket.shutdown(socket.SHUT_WR)  # 송신 종료
            return True
            
        except Exception:
            # 연결 실패는 정상적인 상황 (리스너가 없음)
            return False
        finally:
            try:
                client_socket.close()
            except:
                pass

# 메시지 타입 상수
class MessageTypes:
    PATTERN_UPDATED = "pattern_updated"
    PATTERN_RELOAD_REQUEST = "pattern_reload_request" 
    COLLECTION_COMPLETED = "collection_completed"  # 새로 추가
    HEALTH_CHECK = "health_check"

# 전역 IPC 클라이언트 관리 (서비스별)
_ipc_clients = {}

def get_ipc_client(target_service: str = "pattern_generator") -> IPCClient:
    """서비스별 IPC 클라이언트 인스턴스 반환"""
    global _ipc_clients
    if target_service not in _ipc_clients:
        _ipc_clients[target_service] = IPCClient(target_service=target_service)
    return _ipc_clients[target_service]

def notify_pattern_update(pattern_datetime: datetime, target_service: str = "item_checker"):
    """패턴 업데이트 알림 전송 (일방향) - item_checker에게 알림"""
    client = get_ipc_client(target_service)
    return client.send_notification(
        MessageTypes.PATTERN_UPDATED,
        {'pattern_datetime': pattern_datetime.isoformat()}
    )

def notify_collection_completed(completion_datetime: datetime, target_service: str = "pattern_generator"):
    """데이터 수집 완료 알림 전송 (일방향) - pattern_generator에게 알림"""
    client = get_ipc_client(target_service)
    return client.send_notification(
        MessageTypes.COLLECTION_COMPLETED,
        {'completion_datetime': completion_datetime.isoformat()}
    )