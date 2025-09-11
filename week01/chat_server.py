#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading


def send_whisper(sender_name, target_name, text, sockets_by_name, sender_sock):
    """
    귓속말 전송 함수(보너스 과제).
    - sender_name: 보낸 사람 닉네임
    - target_name: 받을 사람 닉네임
    - text: 메시지 본문
    - sockets_by_name: {닉네임: 소켓} 매핑
    - sender_sock: 보낸 사람 소켓 (확인 메시지 전송용)
    """
    
    
    target_sock = sockets_by_name.get(target_name)
    if target_sock is None:
        try:
            sender_sock.sendall(
                f'시스템> 닉네임 \'{target_name}\' 사용자를 찾을 수 없습니다.\n'.encode('utf-8')
            )
        except OSError:
            pass
        return

    whisper_to_target = f'(귓속말) {sender_name}> {text}\n'
    whisper_to_sender = f'(귓속말) {sender_name} -> {target_name}> {text}\n'

    try:
        target_sock.sendall(whisper_to_target.encode('utf-8'))
    except OSError:
        # 대상 전송 실패 시, 보낸 이에게만 알림
        try:
            sender_sock.sendall('시스템> 전송 실패(상대 연결 상태를 확인하세요).\n'.encode('utf-8'))
        except OSError:
            pass
        return

    try:
        sender_sock.sendall(whisper_to_sender.encode('utf-8'))
    except OSError:
        pass


class ChatServer:
    """
    멀티스레드 TCP 채팅 서버.
    - 접속 시 닉네임을 받아 전체 공지('~~님이 입장하셨습니다.') 방송
    - '/종료' 입력 시 연결 종료 처리 및 퇴장 방송
    - 일반 메시지는 '사용자> 메시지' 형식으로 전체 방송
    - 귓속말: '/w 대상닉 메시지...', '/whisper 대상닉 메시지...', '/귓속말 대상닉 메시지...'
    """

    def __init__(self, host='0.0.0.0', port=5000):
        self.host = host
        self.port = port

        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM) # TCP 소켓 생성, IPv4/TCP 사용
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port)) # ip 소켓 포트에 바인딩
        self.server_sock.listen(20) # 연결 대기열 생성. server_sock을 수신 대기 상태로 설정한다.

        # 동시성 보호용 락
        self.clients_lock = threading.Lock()
        # 소켓 -> 닉네임
        self.name_by_sock = {}
        # 닉네임 -> 소켓
        self.sockets_by_name = {}

        print(f'시스템> 서버 시작: {self.host}:{self.port}')

    def start(self):
        try:
            while True:
                client_sock, addr = self.server_sock.accept()
                t = threading.Thread(
                    target=self.handle_client,
                    args=(client_sock, addr),
                    daemon=True
                )
                t.start()
        except KeyboardInterrupt:
            print('\n시스템> 서버 종료 중...')
        finally:
            self.shutdown()

    def shutdown(self):
        with self.clients_lock:
            for s in list(self.name_by_sock.keys()):
                try:
                    s.close()
                except OSError:
                    pass
            self.name_by_sock.clear()
            self.sockets_by_name.clear()
        try:
            self.server_sock.close()
        except OSError:
            pass
        print('시스템> 서버가 종료되었습니다.')

    def handle_client(self, client_sock, addr):
        try:
            client_sock.sendall('닉네임을 입력하세요: '.encode('utf-8'))
            name = self._negotiate_unique_name(client_sock)
            if not name:
                client_sock.close()
                return

            with self.clients_lock:
                self.name_by_sock[client_sock] = name
                self.sockets_by_name[name] = client_sock

            self.broadcast(f'{name}님이 입장하셨습니다.')

            while True:
                data = client_sock.recv(4096)
                if not data:
                    # 소켓 정상 종료
                    break

                msg = data.decode('utf-8', errors='ignore').strip()
                if not msg:
                    continue

                if msg == '/종료':
                    # 클라이언트 종료 요청
                    break

                if self._is_whisper_command(msg):
                    target, text = self._parse_whisper(msg)
                    if target and text:
                        send_whisper(
                            sender_name=name,
                            target_name=target,
                            text=text,
                            sockets_by_name=self.sockets_by_name,
                            sender_sock=client_sock
                        )
                    else:
                        try:
                            client_sock.sendall(
                                '시스템> 사용법: /w 대상닉네임 메시지\n'.encode('utf-8')
                            )
                        except OSError:
                            pass
                    continue

                # 일반 메시지 방송
                self.broadcast(f'{name}> {msg}')

        except ConnectionResetError:
            # 강제 종료
            pass
        finally:
            # 정리 및 퇴장 방송
            self._remove_client(client_sock)

    def broadcast(self, message):
        """
        전체 클라이언트에게 메시지 방송.
        """
        payload = (message + '\n').encode('utf-8')
        with self.clients_lock:
            dead_sockets = []
            for s in self.name_by_sock.keys():
                try:
                    s.sendall(payload)
                except OSError:
                    dead_sockets.append(s)

            for s in dead_sockets:
                self._unsafe_remove(s)

    def _negotiate_unique_name(self, client_sock):
        """
        중복되지 않는 닉네임을 받을 때까지 요청한다.
        연결이 끊기면 None 반환.
        """
        while True:
            data = client_sock.recv(4096)
            if not data:
                return None
            name = data.decode('utf-8', errors='ignore').strip()
            if not name:
                try:
                    client_sock.sendall('닉네임은 공백일 수 없습니다. 다시 입력: '.encode('utf-8'))
                except OSError:
                    return None
                continue

            with self.clients_lock:
                if name in self.sockets_by_name:
                    try:
                        client_sock.sendall(
                            '이미 사용 중인 닉네임입니다. 다른 닉네임을 입력: '.encode('utf-8')
                        )
                    except OSError:
                        return None
                    continue
                return name

    def _is_whisper_command(self, msg):
        """
        귓속말 명령 여부 판단.
        """
        lowered = msg.lower()
        return lowered.startswith('/w ') or lowered.startswith('/whisper ') or lowered.startswith('/귓속말 ')

    def _parse_whisper(self, msg):
        """
        귓속말 파싱: '/w 대상닉 메시지...' 형태.
        반환: (대상닉, 메시지본문) 혹은 (None, None)
        """
        parts = msg.split(' ', 2)
        if len(parts) < 3:
            return None, None
        # parts[0] = '/w' or '/whisper' or '/귓속말'
        target = parts[1].strip()
        text = parts[2].strip()
        if not target or not text:
            return None, None
        return target, text

    def _remove_client(self, client_sock):
        """
        클라이언트 퇴장 처리 및 방송.
        """
        name = None
        with self.clients_lock:
            name = self.name_by_sock.get(client_sock)
            self._unsafe_remove(client_sock)

        if name:
            self.broadcast(f'{name}님이 퇴장하셨습니다.')

        try:
            client_sock.close()
        except OSError:
            pass

    def _unsafe_remove(self, client_sock):
        """
        락이 잡힌 상태에서만 호출. 내부 맵에서 소켓 제거.
        """
        name = self.name_by_sock.pop(client_sock, None)
        if name is not None:
            self.sockets_by_name.pop(name, None)


def main():
    server = ChatServer(host='0.0.0.0', port=5000)
    server.start()


if __name__ == '__main__':
    main()
