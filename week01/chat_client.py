#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import socket
import threading
import sys


class ChatClient:
    """
    간단한 콘솔 클라이언트.
    - 서버 접속 후 안내에 따라 닉네임을 입력
    - 일반 메시지/귓속말/종료 명령 전송
    """

    def __init__(self, host='127.0.0.1', port=5000):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.receiver_thread = None
        self.running = False

    def start(self):
        self.sock.connect((self.host, self.port))
        self.running = True

        self.receiver_thread = threading.Thread(target=self._recv_loop, daemon=True)
        self.receiver_thread.start()

        try:
            while self.running:
                line = sys.stdin.readline()
                if not line:
                    # EOF
                    self.stop()
                    break

                msg = line.rstrip('\n')
                try:
                    self.sock.sendall((msg + '\n').encode('utf-8'))
                except OSError:
                    print('시스템> 서버와의 연결이 종료되었습니다.')
                    self.stop()
                    break

                if msg == '/종료':
                    self.stop()
                    break
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        if not self.running:
            return
        self.running = False
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self.sock.close()
        except OSError:
            pass

    def _recv_loop(self):
        try:
            while self.running:
                data = self.sock.recv(4096)
                if not data:
                    print('시스템> 서버가 연결을 종료했습니다.')
                    self.stop()
                    break
                text = data.decode('utf-8', errors='ignore')
                # 서버가 '닉네임을 입력하세요: '를 보낼 수 있으므로 그대로 출력
                sys.stdout.write(text)
                sys.stdout.flush()
        except OSError:
            pass
        finally:
            self.running = False


def main():
    host = '127.0.0.1'
    port = 5000

    # 간단한 인자 처리 (표준 라이브러리만 사용)
    if len(sys.argv) >= 2:
        host = sys.argv[1]
    if len(sys.argv) >= 3:
        try:
            port = int(sys.argv[2])
        except ValueError:
            print('사용법: python chat_client.py [HOST] [PORT]')
            sys.exit(1)

    client = ChatClient(host=host, port=port)
    client.start()


if __name__ == '__main__':
    main()
