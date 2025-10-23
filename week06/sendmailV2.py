#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
사용방법 (확장판)
- 기존 단건/소수 전송(원본과 동일):
  python sendmail.py --username '본인' --to 'a@ex.com' --subject '제목' --text '본문'

- CSV 대량 전송(헤더: 이름,이메일):
  python sendmail.py \
    --username 'you@gmail.com' \
    --host 'smtp.gmail.com' --port 587 \
    --subject '세미나 안내' \
    --html-file 'mail.html' --text-file 'mail.txt' \
    --csv 'mail_target_list.csv' \
    --mode 'loop' --verbose
    
  -> 네이버 보낼떄는 아래와 같이 --from 명시 필요
    python sendmail.py \
        --username '{아이디}@naver.com' `
        --host 'smtp.naver.com' --port 465 --ssl `
        --subject '세미나 안내' `
        --html-file '.\week06\mail.html' `
        --text-file '.\week06\mail.txt' `
        --csv '.\week06\mail_target_list.csv' `
        --from 'fhqhxm0727@naver.com' `
        --mode 'loop' --verbose

옵션 설명(신규)
--csv         : '이름,이메일' 형식의 CSV 파일 경로
--mode        : 'loop'(개별 발송, 기본) | 'bcc'(Bcc 동시 발송)
--dry-run     : 실제 전송 없이 CSV/템플릿 파싱 및 치환·요약만 수행
--chunk-size  : bcc 모드에서 한 번에 묶을 수신자 수(기본 50)

주의
- loop 모드만 개인화 치환({name}) 적용.
- bcc 모드는 Bcc 대량 정책/스팸 점수에 영향 가능.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import logging
import mimetypes
import re
import smtplib
import ssl
import sys
from pathlib import Path
from typing import Iterable, List, Dict, Optional, Tuple

try:
    import emails  # python-emails
except ImportError:
    print("필요 패키지 'emails'가 없습니다. 먼저 'pip install emails'를 실행하세요.", file=sys.stderr)
    sys.exit(2)


LOG = logging.getLogger('sendmail')
EMAIL_REGEX = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


# -----------------------------
# 경로/인코딩 유틸
# -----------------------------
def resolve_resource_path(raw: Optional[str]) -> Optional[str]:
    """파일 경로를 안전하게 해석한다.
    - 주어진 경로가 그대로 존재하면 사용
    - 없으면 스크립트 파일의 폴더 기준으로 재탐색
    - 파일명만 주어진 경우에도 스크립트 폴더에서 탐색
    """
    if not raw:
        return None

    p = Path(raw)
    if p.is_absolute() and p.exists():
        return str(p.resolve())
    if p.exists():
        return str(p.resolve())

    script_dir = Path(__file__).resolve().parent
    alt = script_dir / p
    if alt.exists():
        return str(alt.resolve())

    alt2 = script_dir / p.name
    if p.name and alt2.exists():
        return str(alt2.resolve())

    raise FileNotFoundError(f'파일을 찾을 수 없습니다: {raw} (시도: {alt}, {alt2})')


def candidate_encodings(preferred: Optional[str]) -> List[str]:
    order = [preferred or 'utf-8-sig', 'utf-8-sig', 'utf-8', 'cp949', 'euc-kr', 'utf-16']
    seen: set[str] = set()
    out: List[str] = []
    for enc in order:
        if enc and enc not in seen:
            out.append(enc)
            seen.add(enc)
    return out


# -----------------------------
# SMTP 설정
# -----------------------------
class SmtpConfig:
    def __init__(self, host: str, port: int, use_ssl: bool, timeout: int) -> None:
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.timeout = timeout

    def to_emails_smtp_dict(self, username: str, password: str) -> dict:
        cfg = {
            'host': self.host,
            'port': self.port,
            'user': username,
            'password': password,
            'timeout': self.timeout,
        }
        if self.use_ssl:
            cfg['ssl'] = True
            cfg['tls'] = False
        else:
            cfg['ssl'] = False
            cfg['tls'] = True
        return cfg

    def __repr__(self) -> str:
        return f'SmtpConfig(host={self.host!r}, port={self.port!r}, use_ssl={self.use_ssl!r}, timeout={self.timeout!r})'


# -----------------------------
# 인자 파싱/로깅
# -----------------------------
def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='emails 패키지로 HTML/CSV 대량 메일 발송')

    # 발신/수신/제목
    p.add_argument('--from', dest='sender', required=False, help='From 헤더(미지정 시 --username)')
    p.add_argument('--to', dest='to', nargs='*', default=[], help='수신자(비 CSV 모드용, 공백/쉼표 혼용 가능)')
    p.add_argument('--cc', dest='cc', nargs='*', default=[], help='참조')
    p.add_argument('--bcc', dest='bcc', nargs='*', default=[], help='숨은참조')
    p.add_argument('--subject', required=True, help='제목')
    p.add_argument('--reply-to', dest='reply_to', default=None, help='Reply-To(옵션)')

    # 본문
    p.add_argument('--text', dest='text', default=None, help='평문 본문 문자열')
    p.add_argument('--text-file', dest='text_file', default=None, help='평문 본문 파일')
    p.add_argument('--html', dest='html', default=None, help='HTML 본문 문자열')
    p.add_argument('--html-file', dest='html_file', default=None, help='HTML 본문 파일')

    # 첨부
    p.add_argument('--attach', dest='attachments', action='append', default=[], help='첨부 파일(여러 번 지정 가능)')

    # SMTP
    p.add_argument('--username', required=True, help='SMTP 계정(이메일 주소)')
    p.add_argument('--password', required=False, help='SMTP 비밀번호(미지정 시 프롬프트)')
    p.add_argument('--host', default='smtp.gmail.com', help='SMTP 호스트')
    p.add_argument('--port', default=587, type=int, help='SMTP 포트(587/TLS 또는 465/SSL)')
    p.add_argument('--ssl', dest='use_ssl', action='store_true', help='SSL(465) 사용')
    p.add_argument('--timeout', default=30, type=int, help='타임아웃(초)')

    # CSV 대량 발송
    p.add_argument('--csv', dest='csv_path', default=None, help='CSV 경로(헤더: 이름,이메일)')
    p.add_argument('--mode', choices=['loop', 'bcc'], default='loop', help='loop=개별(권장) | bcc=동시')
    p.add_argument('--chunk-size', type=int, default=50, help='bcc 모드 배치 크기')
    p.add_argument('--encoding', default='utf-8-sig', help='CSV 기본 인코딩(기본 utf-8-sig)')

    # 기타
    p.add_argument('--dry-run', action='store_true', help='전송 없이 파싱만')
    p.add_argument('--verbose', action='store_true', help='디버그 로그')

    args = p.parse_args(argv)

    if not any((args.text, args.text_file, args.html, args.html_file)):
        p.error('본문 없음: --text/--text-file/--html/--html-file 중 하나 이상 필요')

    if not args.csv_path and not args.to:
        p.error('수신자 없음: --csv 또는 --to 지정')

    return args


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='[%(levelname)s] %(message)s')


def split_address_args(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    for it in items:
        for part in it.split(','):
            part = part.strip()
            if part:
                out.append(part)
    return out


# -----------------------------
# 본문/CSV/이메일 유틸
# -----------------------------
def read_text_file(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def resolve_bodies(text: Optional[str], text_file: Optional[str], html: Optional[str], html_file: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    text_body = text
    html_body = html

    if text_file:
        tpath = Path(resolve_resource_path(text_file))
        text_body = read_text_file(tpath)

    if html_file:
        hpath = Path(resolve_resource_path(html_file))
        html_body = read_text_file(hpath)

    if text_body is None and html_body is None:
        raise ValueError('본문 해석 실패: text/html 어느 하나도 제공되지 않음')
    return text_body, html_body


def normalize_header_name(name: str) -> str:
    return name.strip().lower()


def parse_csv(path: str, preferred_encoding: str = 'utf-8-sig') -> List[Dict[str, str]]:
    targets: List[Dict[str, str]] = []
    p = Path(resolve_resource_path(path))
    if not p.exists():
        raise FileNotFoundError(f'CSV 파일을 찾을 수 없습니다: {path}')

    last_exc: Optional[Exception] = None
    for enc in candidate_encodings(preferred_encoding):
        try:
            with p.open('r', encoding=enc, newline='') as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None:
                    raise ValueError('CSV 헤더가 없습니다. 첫 줄에 "이름,이메일"을 포함하세요.')

                field_map = {normalize_header_name(h): h for h in reader.fieldnames}
                name_key = field_map.get('이름') or field_map.get('name')
                email_key = field_map.get('이메일') or field_map.get('email')
                if not name_key or not email_key:
                    raise ValueError('CSV 헤더에 "이름,이메일" 또는 "name,email"이 필요합니다.')

                for row in reader:
                    raw_name = (row.get(name_key) or '').strip()
                    raw_email = (row.get(email_key) or '').strip().replace(' ', '')
                    if not raw_name or not raw_email:
                        LOG.warning('이름/이메일 누락 행 건너뜀: %s', row)
                        continue
                    if not EMAIL_REGEX.match(raw_email):
                        LOG.warning('이메일 형식 오류 건너뜀: %s', raw_email)
                        continue
                    targets.append({'name': raw_name, 'email': raw_email})

                LOG.info('CSV 인코딩 감지: %s', enc)
                return targets
        except UnicodeDecodeError as exc:
            last_exc = exc
            continue

    raise UnicodeDecodeError(
        f'CSV 디코딩 실패(시도 인코딩: {candidate_encodings(preferred_encoding)})',
        b'',
        0,
        1,
        'decode failed'
    ) from last_exc


def personalize(template: Optional[str], name: str) -> Optional[str]:
    if template is None:
        return None
    return template.replace('{name}', name)


def build_message(sender: str, subject: str, text_body: Optional[str], html_body: Optional[str]) -> emails.Message:
    """emails.Message 객체를 생성해 반환한다.
    헤더 직접 접근은 하지 않으며, 수신자 지정은 send() 단계에서 처리한다.
    """
    msg = emails.Message(
        subject=subject,
        mail_from=sender,
        text=text_body if text_body else None,
        html=html_body if html_body else None,
    )
    return msg


def add_attachments(msg: emails.Message, paths: Iterable[str]) -> None:
    for raw in paths or []:
        if not raw:
            continue
        p = Path(resolve_resource_path(raw))
        if not p.is_file():
            raise FileNotFoundError(f'첨부 파일을 찾을 수 없습니다: {p}')

        ctype, _ = mimetypes.guess_type(p.name)
        maintype, subtype = ('application', 'octet-stream') if not ctype else ctype.split('/', 1)
        data = p.read_bytes()
        msg.attach(filename=p.name, data=data, maintype=maintype, subtype=subtype)
        LOG.debug('첨부 추가: %s (%s/%s, %d bytes)', p.name, maintype, subtype, len(data))


def send_via_emails(msg: emails.Message, username: str, password: str, config: SmtpConfig, to: List[str], cc: Optional[List[str]] = None, bcc: Optional[List[str]] = None) -> object:
    """emails.Message.send() 호출 래퍼.
    일부 버전에서 cc/bcc 인자를 지원하지 않을 수 있어 폴백 처리한다.
    """
    smtp_dict = config.to_emails_smtp_dict(username=username, password=password)
    try:
        return msg.send(to=to, cc=cc, bcc=bcc, smtp=smtp_dict)
    except TypeError:
        # cc/bcc 인자를 지원하지 않는 버전인 경우: 수신자 리스트에 합쳐서 전송
        merged = list(to or [])
        if cc:
            merged.extend(cc)
        if bcc:
            merged.extend(bcc)
        return msg.send(to=merged, smtp=smtp_dict)


# -----------------------------
# 발송 모드
# -----------------------------
def run_mode_bcc(username: str, password: str, cfg: SmtpConfig, sender: str, subject: str, text_body: Optional[str], html_body: Optional[str], cc: List[str], bcc_fixed: List[str], csv_targets: List[Dict[str, str]], chunk_size: int, dry_run: bool, attachments: List[str]) -> int:
    all_rcpts = [t['email'] for t in csv_targets]
    LOG.info('Bcc 대상: %d명', len(all_rcpts))

    if dry_run:
        LOG.info('[DRY-RUN] bcc=%d, cc=%d', len(all_rcpts) + len(bcc_fixed), len(cc))
        return 0

    if not all_rcpts:
        LOG.warning('Bcc 대상이 없습니다.')
        return 0

    total_ok = 0
    total_fail = 0

    for i in range(0, len(all_rcpts), max(1, chunk_size)):
        batch = all_rcpts[i:i + chunk_size]
        msg = build_message(sender=sender, subject=subject, text_body=text_body, html_body=html_body)
        add_attachments(msg, attachments)

        # To에는 발신자(표시용)만 넣고, 실제 수신자는 bcc로
        to_list = [sender]
        cc_list = cc or []
        bcc_list = batch + (bcc_fixed or [])

        try:
            resp = send_via_emails(msg, username, password, cfg, to=to_list, cc=cc_list, bcc=bcc_list)
            code = getattr(resp, 'status_code', None)
            LOG.info('Bcc 배치 전송 %d명 완료%s', len(batch), f' (status_code={code})' if code else '')
            total_ok += len(batch)
        except Exception as exc:
            LOG.error('Bcc 배치 전송 실패(%d명): %s', len(batch), exc)
            total_fail += len(batch)

    LOG.info('Bcc 전체 결과: 성공 %d / 실패 %d', total_ok, total_fail)
    return 0 if total_fail == 0 else 1


def run_mode_loop(username: str, password: str, cfg: SmtpConfig, sender: str, subject: str, text_tmpl: Optional[str], html_tmpl: Optional[str], cc: List[str], bcc_fixed: List[str], csv_targets: List[Dict[str, str]], dry_run: bool, attachments: List[str]) -> int:
    success = 0
    failed = 0

    for idx, t in enumerate(csv_targets, start=1):
        name = t['name']
        email_addr = t['email']

        text_body = personalize(text_tmpl, name)
        html_body = personalize(html_tmpl, name)

        msg = build_message(sender=sender, subject=subject, text_body=text_body, html_body=html_body)
        add_attachments(msg, attachments)

        to_list = [email_addr]
        cc_list = cc or []
        bcc_list = bcc_fixed or []

        if dry_run:
            LOG.info('[DRY-RUN] (%d/%d) %s <%s>', idx, len(csv_targets), name, email_addr)
            success += 1
            continue

        try:
            resp = send_via_emails(msg, username, password, cfg, to=to_list, cc=cc_list, bcc=bcc_list)
            code = getattr(resp, 'status_code', None)
            LOG.info('성공: %s <%s>%s', name, email_addr, f' (status_code={code})' if code else '')
            success += 1
        except Exception as exc:
            LOG.error('실패: %s <%s> (%s)', name, email_addr, exc)
            failed += 1

    LOG.info('루프 전체 결과: 성공 %d / 실패 %d', success, failed)
    return 0 if failed == 0 else 1


# -----------------------------
# 엔트리포인트
# -----------------------------
def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    configure_logging(args.verbose)

    sender = args.sender or args.username
    to = split_address_args(args.to)
    cc = split_address_args(args.cc)
    bcc = split_address_args(args.bcc)

    # 경로 정규화(파일명만 줘도 스크립트 폴더 기준으로 탐색)
    args.html_file = resolve_resource_path(args.html_file) if args.html_file else None
    args.text_file = resolve_resource_path(args.text_file) if args.text_file else None
    args.csv_path = resolve_resource_path(args.csv_path) if args.csv_path else None
    args.attachments = [resolve_resource_path(x) for x in (args.attachments or [])]

    # 본문 로드
    try:
        text_body, html_body = resolve_bodies(args.text, args.text_file, args.html, args.html_file)
    except Exception as exc:
        LOG.error('본문 처리 오류: %s', exc)
        return 1

    password = args.password or getpass.getpass('SMTP 비밀번호(앱 비밀번호 권장): ')

    cfg = SmtpConfig(host=args.host, port=args.port, use_ssl=args.use_ssl, timeout=args.timeout)

    # CSV 모드
    if args.csv_path:
        try:
            targets = parse_csv(args.csv_path, preferred_encoding=args.encoding)
        except Exception as exc:
            LOG.error('CSV 처리 오류: %s', exc)
            return 1

        if args.mode == 'bcc':
            return run_mode_bcc(
                username=args.username,
                password=password,
                cfg=cfg,
                sender=sender,
                subject=args.subject,
                text_body=text_body,
                html_body=html_body,
                cc=cc,
                bcc_fixed=bcc,
                csv_targets=targets,
                chunk_size=args.chunk_size,
                dry_run=args.dry_run,
                attachments=args.attachments,
            )
        else:
            return run_mode_loop(
                username=args.username,
                password=password,
                cfg=cfg,
                sender=sender,
                subject=args.subject,
                text_tmpl=text_body,
                html_tmpl=html_body,
                cc=cc,
                bcc_fixed=bcc,
                csv_targets=targets,
                dry_run=args.dry_run,
                attachments=args.attachments,
            )

    # 비-CSV(원래 모드): --to 필수
    if not to:
        LOG.error('수신자가 없습니다. --csv 또는 --to 를 지정하세요.')
        return 1

    try:
        msg = build_message(sender=sender, subject=args.subject, text_body=text_body, html_body=html_body)
        add_attachments(msg, args.attachments)
    except FileNotFoundError as exc:
        LOG.error('첨부/본문 파일 오류: %s', exc)
        return 1
    except Exception as exc:
        LOG.error('메시지 구성 오류: %s', exc)
        return 1

    recipients_to = to
    recipients_cc = cc or []
    recipients_bcc = bcc or []

    try:
        resp = send_via_emails(msg, username=args.username, password=password, config=cfg, to=recipients_to, cc=recipients_cc, bcc=recipients_bcc)
        code = getattr(resp, 'status_code', None)
        LOG.info('메일 전송 완료%s', f' (status_code={code})' if code else '')
        return 0
    except smtplib.SMTPAuthenticationError as exc:
        LOG.error('인증 실패: 2단계 인증 후 발급한 "앱 비밀번호"를 사용하세요. (%s)', exc)
        return 1
    except (smtplib.SMTPConnectError, TimeoutError) as exc:
        LOG.error('연결 실패: 호스트/포트/네트워크 확인 필요. (%s)', exc)
        return 1
    except smtplib.SMTPServerDisconnected as exc:
        LOG.error('서버 연결 종료: %s', exc)
        return 1
    except smtplib.SMTPSenderRefused as exc:
        LOG.error('발신자 주소 거부: %s', exc)
        return 1
    except smtplib.SMTPRecipientsRefused as exc:
        LOG.error('수신자 주소 거부: %s', exc)
        return 1
    except smtplib.SMTPDataError as exc:
        LOG.error('데이터 전송 오류: %s', exc)
        return 1
    except ssl.SSLError as exc:
        LOG.error('SSL/TLS 오류: %s', exc)
        return 1
    except OSError as exc:
        LOG.error('입출력/네트워크 오류: %s', exc)
        return 1
    except Exception as exc:
        LOG.error('예기치 못한 오류: %s', exc)
        return 1


if __name__ == '__main__':
    sys.exit(main())
