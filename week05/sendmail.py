#!/usr/bin/env python3
# -*- coding: utf-8 -*-


"""
사용방법 
python {실행 위치에 따른 경로 기입}/sendmail.py `
>>  --username '본인 이메일' `
>>   --to '보낼 대상 이메일' `
>>   --subject '메일 제목' `
>>   --text '메일 본문'
>>   --verbose `
>>   --attach week05/codyssey.pdf

위 명령어 사용 후,
2차 인증 패스워드를 기입해야함.

본인 이메일의 2차 인증 패스워드가 존재치 아니하는 경우
https://myaccount.google.com/apppasswords
해당 경로로 바로 이동하여 16자리 무작위 패스워드를 발급받아 사용해주세요.

* 참고 : verbose == 진행내역 간략한 로그
attach == 첨부파일 기입

"""

'''
sendmail.py
- python-emails(emails) 라이브러리를 사용하여 SMTP로 메일 전송(평문/HTML/첨부)
- Gmail 권장: smtp.gmail.com:587(STARTTLS) 또는 465(SSL)
- 과제 제약 준수: 메일 관련 외부 패키지(emails)만 사용
- 문자열은 단일 인용부호 기본, PEP 8 스타일 준수
'''

from __future__ import annotations

import argparse
import getpass
import logging
import mimetypes
import smtplib
import ssl
import sys
from pathlib import Path
from typing import Iterable, List, Optional

try:
    import emails  # python-emails
except ImportError:
    print("필요 패키지 'emails'가 없습니다. 먼저 'pip install emails'를 실행하세요.", file=sys.stderr)
    sys.exit(2)


LOG = logging.getLogger('sendmail')


class SmtpConfig:
    '''
    SMTP 접속 설정 (CapWords 네이밍).
    '''
    def __init__(self, host: str, port: int, use_ssl: bool, timeout: int) -> None:
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
        self.timeout = timeout

    def to_emails_smtp_dict(self, username: str, password: str) -> dict:
        '''
        python-emails에서 요구하는 smtp 딕셔너리로 변환.
        - use_ssl True  -> implicit SSL(보통 465)
        - use_ssl False -> STARTTLS(보통 587)
        '''
        smtp_dict: dict = {
            'host': self.host,
            'port': self.port,
            'user': username,
            'password': password,
            'timeout': self.timeout,
        }
        if self.use_ssl:
            smtp_dict['ssl'] = True
            smtp_dict['tls'] = False
        else:
            smtp_dict['ssl'] = False
            smtp_dict['tls'] = True
        return smtp_dict

    def __repr__(self) -> str:
        return (
            f'SmtpConfig(host={self.host!r}, port={self.port!r}, '
            f'use_ssl={self.use_ssl!r}, timeout={self.timeout!r})'
        )


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='python-emails를 사용해 SMTP로 이메일을 전송합니다(Gmail 앱 비밀번호 권장).'
    )

    # 발신/수신/제목
    parser.add_argument('--from', dest='sender', required=False,
                        help='발신자 이메일 주소(헤더 From). 미지정 시 --username 사용')
    parser.add_argument('--to', dest='to', required=True, nargs='+',
                        help='주 수신자(복수 가능, 공백/쉼표 혼용 가능)')
    parser.add_argument('--cc', dest='cc', nargs='*', default=[],
                        help='참조 수신자(옵션)')
    parser.add_argument('--bcc', dest='bcc', nargs='*', default=[],
                        help='숨은참조 수신자(옵션)')
    parser.add_argument('--subject', required=True, help='메일 제목')
    parser.add_argument('--reply-to', dest='reply_to', default=None, help='Reply-To 헤더')

    # 본문(택1 이상)
    parser.add_argument('--text', dest='text', default=None, help='평문 본문 문자열')
    parser.add_argument('--text-file', dest='text_file', default=None, help='평문 본문 파일 경로')
    parser.add_argument('--html', dest='html', default=None, help='HTML 본문 문자열')
    parser.add_argument('--html-file', dest='html_file', default=None, help='HTML 본문 파일 경로')

    # 첨부
    parser.add_argument('--attach', dest='attachments', action='append', default=[],
                        help='첨부 파일 경로(여러 번 지정 가능)')

    # SMTP 인증/접속
    parser.add_argument('--username', required=True, help='SMTP 사용자명(보통 Gmail 주소)')
    parser.add_argument('--password', required=False, help='SMTP 비밀번호(미지정 시 안전 프롬프트)')
    parser.add_argument('--host', default='smtp.gmail.com', help='SMTP 호스트')
    parser.add_argument('--port', default=587, type=int, help='SMTP 포트(587 권장, 또는 465)')
    parser.add_argument('--ssl', dest='use_ssl', action='store_true',
                        help='Implicit SSL(SMTPS, 보통 465) 사용')
    parser.add_argument('--timeout', default=30, type=int, help='연결/전송 타임아웃(초)')

    # 로깅
    parser.add_argument('--verbose', action='store_true', help='디버그 로그 출력')

    args = parser.parse_args(argv)

    # 본문 검증: text/html 중 하나는 반드시 필요
    if not any((args.text, args.text_file, args.html, args.html_file)):
        parser.error('본문이 없습니다. --text/--text-file/--html/--html-file 중 하나 이상 지정하세요.')

    return args


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format='[%(levelname)s] %(message)s')


def split_address_args(items: Iterable[str]) -> List[str]:
    out: List[str] = []
    for it in items:
        # 쉼표 분할 + 공백 정리
        parts = [p.strip() for p in it.split(',')]
        out.extend([p for p in parts if p])
    return out


def read_text_file(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def resolve_bodies(
    text: Optional[str],
    text_file: Optional[str],
    html: Optional[str],
    html_file: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
    text_content: Optional[str] = None
    html_content: Optional[str] = None

    if text_file:
        tpath = Path(text_file)
        if not tpath.is_file():
            raise FileNotFoundError(f'평문 본문 파일을 찾을 수 없습니다: {tpath}')
        text_content = read_text_file(tpath)
    elif text:
        text_content = text

    if html_file:
        hpath = Path(html_file)
        if not hpath.is_file():
            raise FileNotFoundError(f'HTML 본문 파일을 찾을 수 없습니다: {hpath}')
        html_content = read_text_file(hpath)
    elif html:
        html_content = html

    if text_content is None and html_content is None:
        raise ValueError('본문 해석 실패: text/html 어느 하나도 제공되지 않았습니다.')

    return text_content, html_content


def build_message(
    sender: str,
    to: List[str],
    subject: str,
    text: Optional[str],
    html: Optional[str],
    cc: Optional[List[str]] = None,
    bcc: Optional[List[str]] = None,
    reply_to: Optional[str] = None,
) -> emails.Message:
    '''
    emails.Message 생성. Bcc는 헤더에 넣지 않고 전송 대상에만 포함한다.
    '''
    cc = cc or []
    bcc = bcc or []

    # emails.Message는 text/html을 동시에 지정하면 multipart/alternative 구성
    msg = emails.Message(
        subject=subject,
        mail_from=sender,
        text=text if text else None,
        html=html if html else None,
    )

    # 표시용 헤더 세팅
    if to:
        msg.headers['To'] = ', '.join(to)
    if cc:
        msg.headers['Cc'] = ', '.join(cc)
    if reply_to:
        msg.headers['Reply-To'] = reply_to

    return msg


def add_attachments(msg: emails.Message, paths: Iterable[str]) -> None:
    for raw in paths:
        if not raw:
            continue
        p = Path(raw)
        if not p.is_file():
            raise FileNotFoundError(f'첨부 파일을 찾을 수 없습니다: {p}')

        # MIME 타입 추정(못 찾으면 octet-stream)
        ctype, _ = mimetypes.guess_type(p.name)
        maintype, subtype = ('application', 'octet-stream') if not ctype else ctype.split('/', 1)

        data = p.read_bytes()
        msg.attach(filename=p.name, data=data, maintype=maintype, subtype=subtype)
        LOG.debug('첨부 추가: %s (%s/%s, %d bytes)', p.name, maintype, subtype, len(data))


def send_via_emails(
    msg: emails.Message,
    username: str,
    password: str,
    config: SmtpConfig,
    recipients: List[str],
) -> object:
    '''
    python-emails의 send 호출. 성공 시 응답 객체를 반환.
    '''
    smtp_dict = config.to_emails_smtp_dict(username=username, password=password)
    LOG.debug('SMTP 설정: %s', smtp_dict)

    # Bcc는 헤더에 넣지 않고 recipients에만 포함되어야 한다.
    # emails.Message.send는 'to' 인자에 전체 수신자 리스트를 넘겨주면 된다.
    response = msg.send(to=recipients, smtp=smtp_dict)
    return response


def main(argv: Optional[Iterable[str]] = None) -> int:
    
    ## 0단계 - 실행 매개변수 분리하여 저장하기
    args = parse_args(argv)
    configure_logging(args.verbose)

    sender = args.sender or args.username
    to = split_address_args(args.to)
    cc = split_address_args(args.cc)
    bcc = split_address_args(args.bcc)

    try:
        text_body, html_body = resolve_bodies(
            text=args.text,
            text_file=args.text_file,
            html=args.html,
            html_file=args.html_file,
        )
    except Exception as exc:
        LOG.error('본문 처리 오류: %s', exc)
        return 1

    ## 1단계 - 메시지 전송자의 2차 비밀번호 기입받기
    password = args.password or getpass.getpass('SMTP 비밀번호(앱 비밀번호 권장): ')

    ## 2단계 - smtp 접속을 위한 설정 기입
    cfg = SmtpConfig(
        host=args.host,
        port=args.port,
        use_ssl=args.use_ssl,
        timeout=args.timeout,
    )
    
    ## 3단계 - 기입한 설정을 기반으로 전송할 emails.Message 객체를 생성.(본 코드에서 사용한 python.emails에서 메일 전송시 사용하는 규약 클래스입니다.)
    try:
        msg = build_message(
            sender=sender,
            to=to,
            subject=args.subject,
            text=text_body,
            html=html_body,
            cc=cc,
            bcc=bcc,
            reply_to=args.reply_to,
        )
        add_attachments(msg, args.attachments)
    except FileNotFoundError as exc:
        LOG.error('첨부/본문 파일 오류: %s', exc)
        return 1
    except Exception as exc:
        LOG.error('메시지 구성 중 오류: %s', exc)
        return 1

    recipients = [*to, *cc, *bcc]

    ## 4단계(완) - python-emails의 send 메소드를 이용, 구현한 emails.Message를 기반하여 메일을 전송한다. 전송 시, 기입한 2차 비밀번호 이용.
    try:
        resp = send_via_emails(
            msg=msg,
            username=args.username,
            password=password,
            config=cfg,
            recipients=recipients,
        )
        # 응답 객체는 구현에 따라 status_code 속성을 가질 수 있음
        code = getattr(resp, 'status_code', None)
        if code is not None:
            LOG.info('메일 전송 완료(status_code=%s)', code)
        else:
            LOG.info('메일 전송 완료')
        return 0
    except smtplib.SMTPAuthenticationError as exc:
        LOG.error('인증 실패: Gmail 2단계 인증 후 발급한 "앱 비밀번호"를 사용하세요. (%s)', exc)
        return 1
    except (smtplib.SMTPConnectError, TimeoutError) as exc:
        LOG.error('연결 실패: 호스트/포트/네트워크 확인 필요. (%s)', exc)
        return 1
    except smtplib.SMTPServerDisconnected as exc:
        LOG.error('서버가 연결을 종료했습니다: %s', exc)
        return 1
    except smtplib.SMTPSenderRefused as exc:
        LOG.error('발신자 주소 거부: %s', exc)
        return 1
    except smtplib.SMTPRecipientsRefused as exc:
        LOG.error('수신자 주소 거부: %s', exc)
        return 1
    except smtplib.SMTPDataError as exc:
        LOG.error('데이터 전송 오류(용량/정책 등): %s', exc)
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
