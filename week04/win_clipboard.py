# win_clipboard.py
from __future__ import annotations

import platform
import subprocess
import time
import ctypes
from ctypes import wintypes


def set_clipboard(text: str, retries: int = 6, backoff_sec: float = 0.08) -> None:
    """
    Windows에서만 동작. 외부 패키지 없이 클립보드에 텍스트 설정.
    1) 우선 'clip.exe'로 시도 (가장 안정적)
    2) 실패 시 ctypes로 CF_UNICODETEXT 설정 + OpenClipboard 재시도

    :param text: 클립보드에 넣을 문자열
    :param retries: OpenClipboard/ctypes 경로 재시도 횟수
    :param backoff_sec: 재시도 간 대기 시간(초)
    """
    if platform.system() != 'Windows':
        raise RuntimeError('set_clipboard: Windows만 지원합니다.')

    # 1) clip.exe로 시도 (권장 경로)
    try:
        # text=True 로 표준 입력 전달; Windows 한글 로케일에서도 안정적으로 동작
        subprocess.run(['clip'], input=text, text=True, check=True)
        return
    except Exception:
        # clip.exe 이용 실패 시 ctypes 경로로 폴백
        pass

    # 2) ctypes 경로 (CF_UNICODETEXT)
    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # 유니코드(UTF-16LE) + 널 종료
    data = text.encode('utf-16le') + b'\x00\x00'

    for attempt in range(1, retries + 1):
        if user32.OpenClipboard(None):
            try:
                if not user32.EmptyClipboard():
                    # 버퍼 비우기 실패 시에도 재시도
                    pass

                h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if not h_global:
                    raise OSError('GlobalAlloc 실패')

                lock_ptr = kernel32.GlobalLock(h_global)
                if not lock_ptr:
                    kernel32.GlobalFree(h_global)
                    raise OSError('GlobalLock 실패')

                ctypes.memmove(lock_ptr, data, len(data))
                kernel32.GlobalUnlock(h_global)

                if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
                    # SetClipboardData 실패 시 메모리 해제 후 재시도
                    kernel32.GlobalFree(h_global)
                    raise OSError('SetClipboardData 실패')

                # 성공: OS가 핸들 소유권을 가짐 (Free 금지)
                return
            finally:
                user32.CloseClipboard()

        # 다른 프로세스가 클립보드를 잠그고 있는 경우가 흔함 → 잠깐 쉬고 재시도
        time.sleep(backoff_sec)

    raise OSError('OpenClipboard 재시도 초과')
