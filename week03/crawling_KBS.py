#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
사용법 : python {{필요시 파일 위치경로/ ... }} crawling_KBS.py --date 20250925 --rows 20 --bonus


crawling_KBS.py (rev6: XHR 전용 / 파라미터 고정값 반영)

- 루트: div.box.padding-24.field-contents-wrapper.category-main-list   == a
  - 아이템 래퍼: div.box-contents.has-wrap                            == b
    - 앵커: a[href]                                                   == c
      - 제목: c > div.txt-wrapper > p.title
      - 이미지: c > div.thumbnail > img.img[src]
      - 날짜: c > div.txt-wrapper > div.field-writer > span.date  (※ 수정된 정확 경로)

현재 구현은 KBS가 실사용하는 공개 XHR 엔드포인트를 직접 호출하여 JSON을 파싱합니다.
정적 HTML 파싱 관련 함수/변수는 전부 제거했습니다.


가변 파라미터:

--date YYYYMMDD → datetimeBegin={YYYYMMDD}000000, datetimeEnd={YYYYMMDD}235959를 설정

--page, --rows → currentPageNo, rowsPerPage를 설정.

가변 파라미터의 내용은 KBS의 헤드라인 표기용 요청에서 사용하는 실제 requestParam입니다. 
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
from dataclasses import dataclass, asdict
from typing import Any, Iterable, List, Mapping, Optional
from urllib.parse import urlencode, urljoin

import requests
from bs4 import BeautifulSoup  # 보너스(KOSPI)용

# --------------- 상수 ---------------
KBS_BASE = 'https://news.kbs.co.kr'
KBS_XHR_PATH = '/api/getNewsList'
DEFAULT_TIMEOUT = 15  # seconds

# 고정값 (요청자 요구)
FIXED_EXCEPT_PHOTO = 'Y'
FIXED_CONTENTS_CODE = 'ALL'
FIXED_LOCAL_CODE = '00'

DEFAULT_DATE = '20250925'  # YYYYMMDD
DEFAULT_PAGE = 1
DEFAULT_ROWS = 12

NAVER_KOSPI_URL = 'https://finance.naver.com/sise/sise_index.naver?code=KOSPI'


# --------------- 데이터 클래스 ---------------
@dataclass
class CrawlingResult:
    title: str
    image_src: str
    date: str
    link: str

    def __str__(self) -> str:
        return (
            f'[제목] {self.title}\n'
            f'  - 이미지: {self.image_src}\n'
            f'  - 날짜  : {self.date}\n'
            f'  - 링크  : {self.link}'
        )


# --------------- 로깅 ---------------
logger = logging.getLogger('kbs_crawler')


def setup_logging(debug: bool) -> None:
    level = logging.DEBUG if debug else logging.INFO
    logger.setLevel(level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    fmt = logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s', '%H:%M:%S')
    handler.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(handler)


# --------------- 유틸 ---------------
def clean_text(text: str) -> str:
    text = text.replace('\xa0', ' ').strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def _first_key(d: Mapping[str, Any], keys: Iterable[str]) -> Optional[Any]:
    for k in keys:
        if k in d and d[k] not in (None, ''):
            return d[k]
    return None


def _to_abs_url(u: str) -> str:
    """
    URL 보정 유틸.
    - 숫자만 들어오면 KBS ncd로 간주하여 /news/view.do?ncd={id} 절대 URL 반환
    - // 로 시작하면 https: 붙임
    - / 로 시작하면 도메인 결합
    - 나머지는 원문 반환
    """
    if not u:
        return ''
    s = str(u).strip()
    # ncd(숫자)만 전달된 경우 상세보기 링크로 변환
    if s.isdigit():
        return urljoin(KBS_BASE, f'/news/view.do?ncd={s}')
    if s.startswith('//'):
        return 'https:' + s
    if s.startswith('/'):
        return urljoin(KBS_BASE, s)
    return s


# --------------- XHR 호출/파싱 ---------------
def build_xhr_url(date_str: str, page: int, rows: int) -> str:
    begin = f'{date_str}000000'
    end = f'{date_str}235959'
    query = {
        'currentPageNo': page,
        'rowsPerPage': rows,
        'exceptPhotoYn': FIXED_EXCEPT_PHOTO,
        'datetimeBegin': begin,
        'datetimeEnd': end,
        'contentsCode': FIXED_CONTENTS_CODE,
        'localCode': FIXED_LOCAL_CODE,
    }
    url = f'{KBS_BASE}{KBS_XHR_PATH}?{urlencode(query)}'
    logger.debug(f'[build_xhr_url] {query} -> URL={url}')
    return url


def fetch_json(url: str) -> Any:
    logger.debug(f'[fetch_json] 요청 URL: {url}')
    resp = requests.get(
        url,
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            ),
            'Accept': 'application/json,text/plain,*/*',
            'Accept-Language': 'ko,ko-KR;q=0.9,en;q=0.8',
            'Connection': 'close',
        },
        timeout=DEFAULT_TIMEOUT,
    )
    logger.debug(
        f'[fetch_json] 응답 코드: {resp.status_code} / 길이: {len(resp.content)} bytes / '
        f'컨텐츠타입: {resp.headers.get("Content-Type")}'
    )
    resp.raise_for_status()
    try:
        data = resp.json()
    except Exception:
        logger.exception('[fetch_json] JSON 디코드 실패')
        raise
    logger.debug(f'[fetch_json] JSON 최상위 타입: {type(data).__name__}')
    return data


def parse_results_from_json(data: Any) -> List[CrawlingResult]:
    """
    다양한 JSON 스키마를 견디도록 후보 키를 폭넓게 탐색한다.
    """
    # 목록 컨테이너 후보
    candidates = []
    if isinstance(data, list):
        candidates = data
    elif isinstance(data, dict):
        for key in ('items', 'list', 'data', 'result', 'rows', 'contents', 'newsList', 'body'):
            if key in data and isinstance(data[key], list):
                candidates = data[key]
                logger.debug(f'[parse_results_from_json] 목록 키 감지: "{key}" / 길이: {len(candidates)}')
                break
        if not candidates:
            # dict 값 중 리스트 탐색
            for v in data.values():
                if isinstance(v, list):
                    candidates = v
                    logger.debug(f'[parse_results_from_json] 값에서 리스트 감지 / 길이: {len(candidates)}')
                    break

    results: List[CrawlingResult] = []
    item_index = 0

    if not candidates:
        logger.warning('[parse_results_from_json] 목록을 찾지 못함')
        return results

    for i, item in enumerate(candidates):
        if not isinstance(item, dict):
            logger.debug(f'  [json#{i}] dict 아님 -> 스킵 ({type(item).__name__})')
            continue

        # 제목
        title_str = clean_text(str(item.get('newsTitle', '')))

        # 이미지
        img_src   = _to_abs_url(str(item.get('imgUrl', '')))

        # 날짜
        date_text = clean_text(str(item.get('deskTime', '')))
        
        # 링크
        link_str =_to_abs_url(str(item.get('newsCode', '')))

        result = CrawlingResult(title=title_str, image_src=img_src, date=date_text, link=link_str)
        logger.info(f'{item_index}번째 객체 생성 : {asdict(result)}')
        results.append(result)
        item_index += 1

    logger.debug(f'[parse_results_from_json] 결과 수: {len(results)}')
    return results


# --------------- 보너스(KOSPI) ---------------
def get_kospi_index() -> str:
    logger.debug('[get_kospi_index] 네이버 금융 요청')
    resp = requests.get(NAVER_KOSPI_URL, timeout=DEFAULT_TIMEOUT, headers={
        'User-Agent': 'Mozilla/5.0',
        'Accept-Language': 'ko,ko-KR;q=0.9,en;q=0.8',
    })
    logger.debug(f'[get_kospi_index] 응답 코드: {resp.status_code}, 길이: {len(resp.content)} bytes')
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, 'html.parser')
    for sel in ['#now_value', '.now_value', '.price', '.num']:
        el = soup.select_one(sel)
        logger.debug(f'[get_kospi_index] 셀렉터 "{sel}" -> {"HIT" if el else "MISS"}')
        if el:
            txt = clean_text(el.get_text(' ', strip=True))
            if re.search(r'[\d,]+(\.\d+)?', txt):
                logger.debug(f'[get_kospi_index] 파싱값="{txt}"')
                return txt
    logger.warning('[get_kospi_index] 파싱 실패')
    return ''


# --------------- CLI ---------------
def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description='KBS 헤드라인 크롤러 (rev6, XHR 전용)')
    p.add_argument('--date', default=DEFAULT_DATE, help='YYYYMMDD (기본: 20250925)')
    p.add_argument('--page', type=int, default=DEFAULT_PAGE, help='페이지 번호 (기본: 1)')
    p.add_argument('--rows', type=int, default=DEFAULT_ROWS, help='행 수 (기본: 12)')
    p.add_argument('--bonus', action='store_true', help='KOSPI 지수도 함께 출력')
    p.add_argument('--debug', action='store_true', help='DEBUG 로그')
    return p.parse_args(argv)


def main() -> None:
    args = parse_args()
    setup_logging(debug=args.debug or True)  # 상세 로깅 기본 ON

    logger.info(f'[main] 시작: date={args.date}, page={args.page}, rows={args.rows}')
    try:
        url = build_xhr_url(args.date, args.page, args.rows)
        data = fetch_json(url)
        results = parse_results_from_json(data)
    except Exception:
        logger.exception('[main] 수집 중 오류')
        results = []

    print(f'KBS 헤드라인 목록 (XHR, date={args.date}, page={args.page}):')
    for i, item in enumerate(results, 1):
        print(f'{i:02d}. {item}')

    if args.bonus:
        try:
            kospi = get_kospi_index()
            print('보너스) 현재 KOSPI 지수:', kospi or '(파싱 실패)')
        except Exception:
            logger.exception('[main] KOSPI 지수 수집 중 오류')


if __name__ == '__main__':
    main()
