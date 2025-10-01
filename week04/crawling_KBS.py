"""
동작 방법 : 
python {{ide 루트에 기반한 상대경로 추가}}/crawling_KBS.py --id {{사용할 네이버 아이디}} --pw {{사용할 네이버 비밀번호}} (--headless)
=> --headless 옵션을 사용할 경우, 현 기기 내에서 브라우저를 직접 실행하지 않고 로그인 및 쿠키 획득 프로세스를 진행한다고 합니다.


구현 내역 : 
1. 셀레니움에 기반하여, 네이버 로그인을 수행합니다.
2. 네이버 로그인은 자동화 로그인을 방지하기위해, 자동 로그인이 감지되면 2차인증으로 영수증 내역을 검증하는 추가 인증을 요구합니다.
이를 우회하기 위해 로그인 폼에 기입하는 내역을 클립보드를 통해 붙여넣으면 우회가 가능하다는 글을 확인했습니다.
https://uipath.tistory.com/141

그러나 문제 제약에 따라, requests, selenium을 제외한 외부 라이브러리/패키지는 사용이 불가합니다.
이에  win_clipboard.py라는, 클립보드 기능을 구현한 파이선 코드를 구현하여 클립보드 기능을 구현했습니다.

3. 클립보드 + 셀레니움을 통해 네이버에 로그인하고, 닉네임/이메일/메일배지알림개수/카페배지알림개수 를 print합니다.

4. (여기서부터 보너스 과제) requests의 Session 기능을 이용하여, 현재 로그인한 쿠키내역을 로컬 파일로 저장합니다.

5. 저장한 쿠키파일을 기반으로, 네이버 메일이 사용자의 메일 목록을 불러오기위해 사용하는 다음 POST 요청을 수행합니다.
https://mail.naver.com/json/list?folderSN=0&page=1&viewMode=time&previewMode=1&sortField=1&sortType=0&u={{argument로 기입된 네이버 아이디}}

6. 해당 엔드포인트에 대한 POST 요청을 Session으로 빼둔 쿠키와 함께 전송하여, 메일 목록 1페이지를 받아와 json을 파싱하여
subject(제목), receivedTime(받은 시각)을 얻습니다.
receivedTime은 사용자가 확인하기에 부정확하므로, 이를 파싱하여 receivedTime_raw(기존값), receivedTime_local(UTC 기반 시간값)으로 표기합니다.


유의사항!!! : 
clipboard 구현 내역이 윈도우에서만 동작합니다... MAC 환경이시라면 테스트가 어렵습니다! 시간이 많지 않아 MAC까지 구현은 힘들거같네요.


기타 내역 : 
셀레니움 기능 도중, 문제가 발생한 경우 문제가 발생한 시점의 html 현황과 스크린샷을 저장하도록 하는 예외처리 기능이 구현되어있습니다.
연월일_시분초_시도한기능명.html / .png 를 참조하시면 확인 가능합니다.(해당 에러는 headless 옵션을 사용할 때만 나타나고있습니다. 이를 픽스해야하나, 시간도 없고.. 예외처리 확인 겸 둔채로 업로드합니다. 
테스트시에는 headless 옵션 제외하고 사용해주세요!)
"""


# crawling_KBS.py  (V3.5)
from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from typing import Final

import requests
from http.cookiejar import LWPCookieJar

from selenium import webdriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException

from win_clipboard import set_clipboard

from datetime import datetime

def _nowstamp() -> str:
    return datetime.now().strftime('%Y%m%d_%H%M%S')

def save_debug(driver, tag: str) -> None:
    """현재 DOM과 스크린샷을 'YYYYMMDD_HHMMSS_tag.(png|html)'로 저장."""
    ts = _nowstamp()
    png = f'{ts}_{tag}.png'
    html = f'{ts}_{tag}.html'
    try:
        driver.save_screenshot(png)
    except Exception:
        pass
    try:
        with open(html, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
    except Exception:
        pass
    print(f'[DEBUG] 캡처 저장: {png} / {html}')



# ===== 계정 정보 (인자로 덮어쓸 수 있음) =====
NAVER_ID: Final[str] = ''
NAVER_PW: Final[str] = ''

# ===== 설정 =====
NAVER_LOGIN_URL: Final[str] = 'https://nid.naver.com/nidlogin.login?mode=form&url=https://www.naver.com/'
DEFAULT_WAIT_SEC: Final[int] = 25
HEADLESS: bool = False  # argparse로 토글

# ===== 선택자 (요청한 클래스 기반 유지) =====
LOGIN_ID_INPUT_CSS: Final[str] = '.input_item.id input'
LOGIN_PW_INPUT_CSS: Final[str] = '.input_item.pw input'
LOGIN_SUBMIT_BTN_CSS: Final[str] = '.btn_login_wrap button[type="submit"]'

# 로그인 성공 후 닉네임/이메일
NICK_CONTAINER_CSS: Final[str] = 'div.MyView-module__user_desc___UWPUY'
NICK_TEXT_CSS: Final[str] = 'div.MyView-module__user_desc___UWPUY span.MyView-module__nickname___fcxwI'
EMAIL_CSS: Final[str] = 'div.MyView-module__desc_email___JwAKa'


# ================= 공통 유틸 =================
def setup_driver() -> webdriver.Chrome:
    print('[STEP] 브라우저 시작')
    opts = webdriver.ChromeOptions()
    if HEADLESS:
        opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1400,1000')
    drv = webdriver.Chrome(options=opts)  # Selenium Manager
    drv.implicitly_wait(2)
    return drv


def paste_via_clipboard(driver: webdriver.Chrome, element, text: str, label: str) -> None:
    try:
        print(f'[CLIP] {label}: 클립보드 설정 시도')
        set_clipboard(text)
        print(f'[CLIP] {label}: 클립보드 설정 완료')

        element.click()
        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
        time.sleep(0.15)

        actions = ActionChains(driver)
        actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
        print(f'[PASTE] {label}: 붙여넣기 수행')
        time.sleep(0.3)

        val = element.get_attribute('value') or ''
        if not val:
            print(f'[WARN] {label}: 비어 있음 → 재시도')
            set_clipboard(text)
            element.click()
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).send_keys('a').key_up(Keys.CONTROL).perform()
            time.sleep(0.1)
            actions = ActionChains(driver)
            actions.key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
            time.sleep(0.3)
            val = element.get_attribute('value') or ''

        print(f'[OK] {label}: 길이={len(val)}')
    except Exception as e:
        print(f'[FAIL] {label}: 입력 중 예외: {e!r}')
        save_debug(driver, f'paste_fail_{label}')
        raise


# ================= 기존 V3 기능들 (유지) =================
def enter_credentials_with_clipboard_and_submit(driver: webdriver.Chrome) -> None:
    try:
        print('[STEP] 로그인 페이지 진입')
        driver.get(NAVER_LOGIN_URL)
        print(f'[OK] 현재 URL: {driver.current_url}')

        print('[STEP] 아이디/비밀번호 입력 필드 대기')
        id_input = WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, LOGIN_ID_INPUT_CSS))
        )
        pw_input = WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, LOGIN_PW_INPUT_CSS))
        )

        print('[STEP] 아이디 붙여넣기(클립보드)')
        paste_via_clipboard(driver, id_input, NAVER_ID, 'ID')

        print('[STEP] 비밀번호 붙여넣기(클립보드)')
        paste_via_clipboard(driver, pw_input, NAVER_PW, 'PW')

        print('[STEP] 로그인 버튼 대기')
        submit_btn = WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, LOGIN_SUBMIT_BTN_CSS))
        )

        print('[STEP] 로그인 버튼 클릭')
        submit_btn.click()
        print('[OK] 로그인 버튼 클릭')

        print('[WAIT] 로그인 응답 대기')
        WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
            EC.any_of(
                EC.url_contains('www.naver.com'),
                EC.staleness_of(submit_btn),
                EC.invisibility_of_element_located((By.CSS_SELECTOR, LOGIN_SUBMIT_BTN_CSS))
            )
        )
        print('[OK] 로그인 응답 감지')
    except Exception as e:
        print(f'[FAIL] 로그인 단계 실패: {e!r}')
        save_debug(driver, 'login_flow_fail')
        raise


def bypass_device_registration(driver) -> None:
    print('[STEP] 기기등록 화면 감지')
    try:
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.ID, 'new.dontsave'))
        )
        el = WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
            EC.element_to_be_clickable((By.ID, 'new.dontsave'))
        )
        try:
            driver.execute_script(
                'arguments[0].scrollIntoView({block:"center", inline:"center"});', el
            )
        except Exception:
            pass

        el.click()
        print('[OK] 기기등록: 등록안함 클릭')

        WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
            EC.any_of(
                EC.staleness_of(el),
                EC.url_contains('www.naver.com'),
                EC.invisibility_of_element_located((By.ID, 'new.dontsave')),
            )
        )
        print('[OK] 기기등록 화면 통과')
    except TimeoutException:
        print('[INFO] 기기등록 화면 미표시 → 건너뜀')
    except Exception as e:
        print(f'[WARN] 기기등록 우회 중 예외 발생: {e!r}')
        save_debug(driver, 'device_reg_bypass_fail')
        # 계속 진행


def print_nickname_if_present(driver: webdriver.Chrome) -> None:
    print('[STEP] 닉네임/이메일 영역 탐색')
    try:
        WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, NICK_CONTAINER_CSS))
        )
        nick_el = WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, NICK_TEXT_CSS))
        )
        nickname = (nick_el.text or '').strip()
        print(f'[OK] 닉네임: {nickname}')

        print('[STEP] 이메일 탐색')
        try:
            email_el = WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, EMAIL_CSS))
            )
            email_text = (email_el.text or '').strip()
            print(f'[OK] 이메일: {email_text}')
        except Exception:
            print('[INFO] 이메일 요소를 찾지 못했습니다.')

    except Exception as e:
        print(f'[FAIL] 닉네임 탐색 실패: {e!r}')
        save_debug(driver, 'nickname_fail')


def get_badge_count(driver, label_texts: list[str]) -> None:
    for label_text in label_texts:
        xpath = (
            "//span[contains(@class,'MyView-module__item_text') and normalize-space()=$label]"
            "/following-sibling::span[contains(@class,'MyView-module__item_num')][1]"
        ).replace("$label", f"'{label_text}'")

        try:
            el = WebDriverWait(driver, DEFAULT_WAIT_SEC).until(
                EC.visibility_of_element_located((By.XPATH, xpath))
            )
            raw = (el.text or "").strip()
            normalized = raw.replace(",", "")
            if normalized.endswith("+"):
                normalized = normalized[:-1]

            if normalized.isdigit():
                print(f"{label_text} 알림: {int(normalized)}")
            else:
                print(f"{label_text} 알림: {raw if raw else '없음'}")
        except Exception as e:
            print(f"[WARN] {label_text} 배지 탐색 실패: {e!r}")
            save_debug(driver, f'badge_fail_{label_text}')
            print(f"{label_text} 알림: 없음")


# ================= 추가: 세션 이관 + 쿠키 저장 + 메일 API 호출 =================
def session_from_selenium(driver: webdriver.Chrome) -> requests.Session:
    """
    Selenium 브라우저에서 네이버 관련 쿠키를 모두 뽑아 requests.Session에 이식하고
    브라우저 UA로 맞춘다. (이 세션은 곧바로 재사용)
    """
    print('[STEP] 세션 이관: Selenium → requests.Session')
    sess = requests.Session()

    # UA 복제
    try:
        ua = driver.execute_script('return navigator.userAgent;') or 'Mozilla/5.0'
    except Exception:
        ua = 'Mozilla/5.0'
    sess.headers.update({'User-Agent': ua, 'Referer': 'https://www.naver.com/'})

    # 쿠키 이식
    copied = 0
    for c in driver.get_cookies():
        dom = c.get('domain', '')
        if 'naver.com' in dom:
            sess.cookies.set(
                name=c['name'],
                value=c['value'],
                domain=dom,
                path=c.get('path', '/'),
            )
            copied += 1
    print(f'[OK] 세션 이관: 쿠키 {copied}개 복사')
    return sess


def save_selenium_cookies_json(driver: webdriver.Chrome, path: str = 'selenium_cookies.json') -> None:
    """Selenium 쿠키를 JSON 파일로 저장."""
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(driver.get_cookies(), f, ensure_ascii=False, indent=2)
    print(f'[OK] Selenium 쿠키 저장: {path}')


def save_requests_cookies_lwp(sess: requests.Session, path: str = 'requests_cookies.lwp') -> None:
    """requests 세션 쿠키를 LWP 포맷으로 저장(표준 라이브러리 CookieJar)."""
    jar = LWPCookieJar()
    # session.cookies(RequestsCookieJar) → LWPCookieJar로 복사
    for c in sess.cookies:
        # LWPCookieJar에 직접 쿠키 추가
        jar.set_cookie(c)
    jar.save(path, ignore_discard=True, ignore_expires=True)
    print(f'[OK] requests 쿠키 저장: {path}')


def warm_up_mail(sess: requests.Session) -> None:
    """
    mail.naver.com에 한 번 접근해 필요한 서브도메인 쿠키를 세팅(안정화).
    """
    print('[STEP] mail.naver.com 워밍업')
    r = sess.get('https://mail.naver.com/', headers={'Referer': 'https://www.naver.com/'}, timeout=10)
    print(f'[OK] 워밍업 status={r.status_code}')


def fetch_mail_page1(sess: requests.Session, user_id: str) -> list[dict]:
    """
    POST https://mail.naver.com/json/list ...
    1페이지 mailData의 subject, receivedTime(raw/해석)을 리스트[dict]로 반환.
    """
    print('[STEP] 메일 목록 1페이지 요청(POST)')
    url = 'https://mail.naver.com/json/list'
    params = {
        'folderSN': 0,
        'page': 1,
        'viewMode': 'time',
        'previewMode': 1,
        'sortField': 1,
        'sortType': 0,
        'u': user_id,
    }
    headers = {
        'Referer': 'https://mail.naver.com/',
        'Accept': 'application/json',
    }
    r = sess.post(url, params=params, headers=headers, timeout=15)
    r.raise_for_status()
    data = r.json()

    mail_data = data.get('mailData', []) or []
    print(f'[OK] 메일 항목 수: {len(mail_data)}')

    kst = timezone(timedelta(hours=9))
    results: list[dict] = []
    for item in mail_data:
        subject = item.get('subject') or ''
        recv_raw = item.get('receivedTime', None)
        if isinstance(recv_raw, int):
            recv_local = datetime.fromtimestamp(recv_raw, tz=kst).strftime('%Y-%m-%d %H:%M:%S %Z')
        else:
            recv_local = None
        results.append({
            'subject': subject,
            'receivedTime_raw': recv_raw,
            'receivedTime_local': recv_local,
        })
    return results


# ================= 메인 흐름 =================
def main() -> None:
    parser = argparse.ArgumentParser(description='Naver login + requests 세션 이관 + 메일 API 호출')
    parser.add_argument('--id', dest='naver_id', default=None, help='Naver ID (미지정 시 코드 상수 사용)')
    parser.add_argument('--pw', dest='naver_pw', default=None, help='Naver PW (미지정 시 코드 상수 사용)')
    parser.add_argument('--headless', action='store_true', help='Headless 모드')
    args = parser.parse_args()

    # 인자로 전달되면 상수 덮어쓰기
    if args.naver_id:
        globals()['NAVER_ID'] = args.naver_id
    if args.naver_pw:
        globals()['NAVER_PW'] = args.naver_pw
    if args.headless:
        globals()['HEADLESS'] = True

    driver = setup_driver()
    try:
        # 1) 로그인(+기기등록 우회) — 기존 로직 유지
        enter_credentials_with_clipboard_and_submit(driver)
        bypass_device_registration(driver)
        print_nickname_if_present(driver)
        get_badge_count(driver, ['메일', '카페'])

        # 2) 세션 이관 + 쿠키 저장
        sess = session_from_selenium(driver)
        save_selenium_cookies_json(driver, 'selenium_cookies.json')
        save_requests_cookies_lwp(sess, 'requests_cookies.lwp')

        # 3) mail.naver.com 워밍업 후 메일 1페이지 수집
        warm_up_mail(sess)
        mail_list = fetch_mail_page1(sess, globals()['NAVER_ID'])

        # 4) 리스트[dict] 출력 (요청사항: 리스트에 json 형태로 저장 후 화면 표기)
        print('=== 메일 1페이지 (subject, receivedTime_raw, receivedTime_local) ===')
        print(json.dumps(mail_list, ensure_ascii=False, indent=2))

    finally:
        print('[STEP] 브라우저 종료')
        driver.quit()


if __name__ == '__main__':
    main()
