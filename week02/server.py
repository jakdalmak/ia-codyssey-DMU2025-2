#!/usr/bin/env python3
"""
http://codyssey-dmu-kkh.duckdns.org:8080//
위 주소에 접속하여 보너스 과제의 출력 결과를 html 내에서 확인 가능하도록 구현해두었습니다.
nginx 등 프록시 관련 구현내역 0
aws를 이용해 구현된 순수한 html 및 지오네이션 확인 목적의 배포 사이트입니다.
"""

"""
멀티스레드 HTTP 서버:
- 포트 8080 리슨(기본)
- / 또는 /index.html: index.html을 200 OK로 반환
- 기타 경로: 404
- POST 등 비허용 메서드: 405 Method Not Allowed (+ Allow 헤더)
- HEAD: 헤더만 200 반환
- 매 요청마다 접속 시간/클라이언트 IP(선택: 경로, UA, 위치정보) 콘솔 로그
- 공인 IP면 간단 지오로케이션(ip-api.com) 시도(표준 urllib/json)
- 프록시/터널 환경에서 X-Forwarded-For / X-Real-IP / CF-Connecting-IP 지원
- 멀티스레드 처리(ThreadingHTTPServer)
- 지오로케이션/접속 로그를 NDJSON(줄당 JSON) 형태로 geo_access.log파일에 json 형식으로 누적 저장
"""

from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from datetime import datetime
from ipaddress import ip_address
from urllib.request import urlopen, Request
from urllib.parse import quote
from typing import Optional, Dict
from functools import lru_cache
import json
import os
import sys
import socket
import logging


DEFAULT_HOST = '0.0.0.0'
DEFAULT_PORT = 8080
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_FILE = os.path.join(BASE_DIR, 'index.html')
READ_BUFFER_SIZE = 64 * 1024  # 64 KiB

# 로그 파일 설정(표준 라이브러리 logging, 스레드 세이프)
LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.environ.get('GEO_LOG_FILE', os.path.join(LOG_DIR, 'geo_access.log'))

GEO_LOGGER = logging.getLogger('geo_logger')

if not GEO_LOGGER.handlers:
    GEO_LOGGER.setLevel(logging.INFO)
    fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
    # 메시지 그대로 한 줄 기록(포맷은 _log_access에서 json.dumps로 구성)
    fh.setFormatter(logging.Formatter('%(message)s'))
    GEO_LOGGER.addHandler(fh)
    GEO_LOGGER.propagate = False


def format_timestamp(dt: datetime) -> str:
    """YYYY-MM-DD HH:MM:SS 형식 문자열로 반환."""
    return dt.strftime('%Y-%m-%d %H:%M:%S')


def is_public_ip(ip: str) -> bool:
    """사설/루프백/예약/링크로컬이 아닌 공인 IP 여부 판단."""
    try:
        addr = ip_address(ip)
        return not (addr.is_private or addr.is_loopback or addr.is_reserved or addr.is_link_local)
    except ValueError:
        return False


@lru_cache(maxsize=256)
def _geolocate_ip_cached(ip: str) -> Optional[Dict[str, str]]:
    """IP별 간단 캐시. 외부 호출을 줄이기 위한 내부 함수."""
    # ip-api.com (무료/제한). 교육·시연용. https 사용 원하면 유료/제한 고려.
    ## 기본 파이선 라이브러리 하에는 구현할 방법이 없다고 해서, 외부 서비스를 사용했습니다. 동작 방법은 명확히 모릅니다.
    url = f'http://ip-api.com/json/{quote(ip)}?fields=status,country,regionName,city,isp,query'
    req = Request(url, headers={'User-Agent': 'Python-urllib/3'})
    with urlopen(req, timeout=1.5) as resp:
        data = json.loads(resp.read().decode('utf-8', errors='replace'))
    if isinstance(data, dict) and data.get('status') == 'success':
        return {
            'country': data.get('country'),
            'region': data.get('regionName'),
            'city': data.get('city'),
            'isp': data.get('isp'),
        }
    return None


def geolocate_ip(ip: str) -> Optional[Dict[str, str]]:
    """
    공인 IP일 때만 간단 지오로케이션 조회(국가/지역/도시/ISP).
    실패하거나 사설/루프백이면 None 반환.
    """
    if not is_public_ip(ip):
        return None
    try:
        return _geolocate_ip_cached(ip)
    except Exception:
        return None


def read_index_bytes(path: str) -> bytes:
    """index.html을 바이트로 읽어 반환. 파일 없으면 FileNotFoundError."""
    with open(path, 'rb') as f:
        return f.read()


class PirateRequestHandler(BaseHTTPRequestHandler):
    """GET/HEAD 요청을 처리하는 멀티스레드용 핸들러."""

    server_version = 'PirateHTTP/1.1'

    # ===== 메서드 디스패치 =====

    def do_GET(self) -> None:
        """GET 처리: / 또는 /index.html 은 로컬 파일 제공, 그 외 404."""
        now = datetime.now()
        client_ip = self._get_client_ip()
        path = self.path or '/'
        ua = self.headers.get('User-Agent', '-')
        location = geolocate_ip(client_ip)

        if path in ('/', '/index.html'):
            try:
                body = read_index_bytes(INDEX_FILE)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Connection', 'close')
                self.end_headers()
                # 대용량 대비 안전 전송(멀티스레드 환경에서도 OK)
                sent = 0
                total = len(body)
                while sent < total:
                    chunk = body[sent:sent + READ_BUFFER_SIZE]
                    self.wfile.write(chunk)
                    sent += len(chunk)
                self._log_access(now, client_ip, path, ua, location, status=200)
            except FileNotFoundError:
                self._send_text(404, 'index.html not found')
                self._log_access(now, client_ip, path, ua, location, status=404)
            except Exception as exc:
                msg = f'Internal server error: {exc}'
                self._send_text(500, msg)
                self._log_access(now, client_ip, path, ua, location, status=500)
        else:
            self._send_text(404, 'Not found')
            self._log_access(now, client_ip, path, ua, location, status=404)

    def do_HEAD(self) -> None:
        """HEAD 처리: 본문 없이 헤더만 송신."""
        now = datetime.now()
        client_ip = self._get_client_ip()
        path = self.path or '/'
        ua = self.headers.get('User-Agent', '-')
        location = geolocate_ip(client_ip)

        if path in ('/', '/index.html'):
            try:
                body = read_index_bytes(INDEX_FILE)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Connection', 'close')
                self.end_headers()
                # 본문은 쓰지 않음
                self._log_access(now, client_ip, path, ua, location, status=200)
            except FileNotFoundError:
                self.send_response(404)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', '0')
                self.send_header('Connection', 'close')
                self.end_headers()
                self._log_access(now, client_ip, path, ua, location, status=404)
            except Exception:
                self.send_response(500)
                self.send_header('Content-Type', 'text/plain; charset=utf-8')
                self.send_header('Content-Length', '0')
                self.send_header('Connection', 'close')
                self.end_headers()
                self._log_access(now, client_ip, path, ua, location, status=500)
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', '0')
            self.send_header('Connection', 'close')
            self.end_headers()
            self._log_access(now, client_ip, path, ua, location, status=404)

    # 비허용 메서드는 405로 응답(Allow 헤더 부착)
    def do_POST(self) -> None:
        self._respond_405()

    def do_PUT(self) -> None:
        self._respond_405()

    def do_DELETE(self) -> None:
        self._respond_405()

    def do_PATCH(self) -> None:
        self._respond_405()

    # ===== 헬퍼 =====

    def _respond_405(self) -> None:
        """허용되지 않은 메서드에 대해 405 반환."""
        body = b'Method Not Allowed'
        self.send_response(405)
        self.send_header('Allow', 'GET, HEAD')
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, code: int, text: str) -> None:
        """간단 텍스트 응답 유틸리티."""
        body = text.encode('utf-8')
        self.send_response(code)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(body)

    def _get_client_ip(self) -> str:
        """
        프록시/터널 환경을 고려해 클라이언트 IP를 결정.
        (과제/시연 목적: 신뢰 검증 없이 단순 채택. 실서비스는 신뢰 프록시 검증 필요)
        """
        xff = self.headers.get('X-Forwarded-For')
        if xff:
            first = xff.split(',')[0].strip()
            if first:
                return first
        xri = self.headers.get('X-Real-IP')
        if xri:
            return xri.strip()
        cfc = self.headers.get('CF-Connecting-IP')
        if cfc:
            return cfc.strip()
        return self.client_address[0] if self.client_address else '-'

    def _log_access(
        self,
        now: datetime,
        ip: str,
        path: str,
        ua: str,
        location: Optional[Dict[str, str]],
        status: int,
    ) -> None:
        """요청 로그 한 줄 출력 + NDJSON 파일 누적 저장."""
        ts = format_timestamp(now)

        # 콘솔용 요약 로그
        parts = [f'[{ts}] ip={ip}', f'path={path}', f'status={status}']
        if location:
            loc_str = f"{location.get('country')}/{location.get('region')}/{location.get('city')}"
            isp = location.get('isp') or '-'
            parts.append(f'loc={loc_str}')
            parts.append(f'isp="{isp}"')
        if ua and ua != '-':
            parts.append(f'user-agent="{ua}"')
        print(' '.join(parts), flush=True)

        # 파일 누적 로그(NDJSON). 위치가 없어도 한 줄씩 기록.
        try:
            entry = {
                'ts': ts,
                'ip': ip,
                'path': path,
                'status': status,
                'ua': ua if ua and ua != '-' else None,
                'country': location.get('country') if location else None,
                'region': location.get('region') if location else None,
                'city': location.get('city') if location else None,
                'isp': location.get('isp') if location else None,
            }
            GEO_LOGGER.info(json.dumps(entry, ensure_ascii=False))
        except Exception:
            # 파일 쓰기 실패가 있더라도 본 응답 흐름은 방해하지 않음
            pass

    # BaseHTTPRequestHandler 기본 로깅 비활성화
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


def main() -> None:
    """서버 실행 엔트리포인트."""
    host = os.environ.get('BIND_HOST', DEFAULT_HOST)
    port_env = os.environ.get('PORT')
    port = int(port_env) if port_env else DEFAULT_PORT

    # 포트 사용 가능성 간단 점검(친절한 오류 메시지)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError as exc:
        print(f'포트 {port} 바인딩 실패: {exc}', file=sys.stderr, flush=True)
        print('다른 프로세스가 사용 중일 수 있습니다.', file=sys.stderr, flush=True)
        sys.exit(1)
    finally:
        sock.close()

    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, PirateRequestHandler)
    bind_info = host if host != '0.0.0.0' else '0.0.0.0(모든 인터페이스)'
    try:
        print(f'HTTP 서버 시작(멀티스레드): http://localhost:{port}/  (바인드: {bind_info})', flush=True)
        print(f'지오 로그 파일: {LOG_FILE}', flush=True)
        print('중지하려면 Ctrl+C 를 누르세요.', flush=True)
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('\n서버 종료 중...', flush=True)
    finally:
        httpd.server_close()
        print('서버가 정상 종료되었습니다.', flush=True)


if __name__ == '__main__':
    main()
