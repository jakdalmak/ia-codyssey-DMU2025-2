#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
간단한 TODO 클라이언트 (보너스 과제용)

서버 스펙 (todo.py 기준)
- 전체 조회   : GET    /todo
- 추가        : POST   /todo          (body: TodoCreate)
- 개별 조회   : GET    /todo/{todo_id}
- 수정        : PUT    /todo/{todo_id} (body: TodoItem)
- 삭제        : DELETE /todo/{todo_id}

Pydantic 모델 (서버 기준)
class TodoCreate(BaseModel):
    title: str
    description: Optional[str] = None
    is_done: bool = False

class TodoItem(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    is_done: Optional[bool] = None

여기 클라이언트에서는 사용자가 "title/description/is_done" 값을
프롬프트로 입력하면, 그걸 JSON으로 변환해서 서버로 보낸다.
사용자는 JSON을 직접 안 쳐도 된다.
"""

import json
from typing import Optional, Dict, Any

from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


BASE_URL = "http://127.0.0.1:8000"
TODO_PATH = "/todo"  # 서버 코드와 동일하게 /todo 로 통일


# ---------------------------------------------------------
# 공통 HTTP 요청 함수
# ---------------------------------------------------------

def send_request(method: str, path: str, data: Optional[Dict[str, Any]] = None):
    """
    단순 HTTP 요청 함수
    - method: "GET", "POST", "PUT", "DELETE" 등
    - path  : "/todo", "/todo/1" 같은 경로
    - data  : JSON 바디로 보낼 dict (없으면 None)
    """
    url = BASE_URL + path
    headers = {"Content-Type": "application/json"}

    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
    else:
        body = None

    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req) as resp:
            raw = resp.read().decode("utf-8")
            if raw:
                try:
                    return json.loads(raw)
                except json.JSONDecodeError:
                    return raw
            return None
    except HTTPError as e:
        print(f"[HTTP Error] {e.code} {e.reason}")
        try:
            err_body = e.read().decode("utf-8")
            if err_body:
                print("서버 응답:", err_body)
        except Exception:
            pass
    except URLError as e:
        print(f"[URL Error] {e.reason}")
    except Exception as e:
        print(f"[Error] {e}")
    return None


# ---------------------------------------------------------
# 각 기능별 클라이언트 함수
# ---------------------------------------------------------

def list_todos():
    """전체 TODO 목록 조회: GET /todo"""
    print("\n[전체 목록 조회]")
    data = send_request("GET", TODO_PATH)
    print("응답:", data)


def _input_bool(prompt: str, default: bool) -> bool:
    """
    y/n 입력 받아서 bool 로 변환
    빈 입력 시 default 사용
    """
    raw = input(f"{prompt} (y/n, 엔터 시 {default}): ").strip().lower()
    if raw == "":
        return default
    if raw in ("y", "yes", "1", "true", "t"):
        return True
    if raw in ("n", "no", "0", "false", "f"):
        return False
    print("인식 못한 값이라 기본값을 사용합니다.")
    return default


def create_todo():
    """TODO 추가: POST /todo"""
    print("\n[TODO 추가]")
    title = input("제목(title)을 입력하세요: ").strip()
    if not title:
        print("title은 비어 있을 수 없습니다. 추가하지 않습니다.")
        return

    description = input("설명(description)을 입력하세요 (엔터 시 생략): ").strip()
    is_done = _input_bool("완료 여부(is_done)", default=False)

    payload = {
        "title": title,
        "description": description if description else None,
        "is_done": is_done,
    }

    data = send_request("POST", TODO_PATH, payload)
    print("응답:", data)


def get_single_todo():
    """개별 조회: GET /todo/{id}"""
    print("\n[개별 조회]")
    todo_id = input("조회할 TODO id를 입력하세요: ").strip()
    if not todo_id.isdigit():
        print("id는 숫자여야 합니다.")
        return

    path = f"{TODO_PATH}/{todo_id}"
    data = send_request("GET", path)
    print("응답:", data)


def update_todo():
    """수정: PUT /todo/{id}"""
    print("\n[TODO 수정]")
    todo_id = input("수정할 TODO id를 입력하세요: ").strip()
    if not todo_id.isdigit():
        print("id는 숫자여야 합니다.")
        return

    print("빈 값으로 두면 해당 필드는 수정하지 않습니다.")
    new_title = input("새 제목(title)을 입력하세요 (엔터 시 유지): ").strip()
    new_description = input("새 설명(description)을 입력하세요 (엔터 시 유지): ").strip()
    change_done = input("완료 여부(is_done)를 수정하겠습니까? (y/n, 엔터 시 n): ").strip().lower()

    payload: Dict[str, Any] = {}

    # TodoItem 의 모든 필드는 Optional 이므로, 보낸 것만 수정됨.
    if new_title != "":
        payload["title"] = new_title
    if new_description != "":
        payload["description"] = new_description

    if change_done in ("y", "yes"):
        new_is_done = _input_bool("새 완료 여부(is_done)", default=False)
        payload["is_done"] = new_is_done

    if not payload:
        print("변경할 필드가 없습니다. 요청을 보내지 않습니다.")
        return

    path = f"{TODO_PATH}/{todo_id}"
    data = send_request("PUT", path, payload)
    print("응답:", data)


def delete_todo():
    """삭제: DELETE /todo/{id}"""
    print("\n[TODO 삭제]")
    todo_id = input("삭제할 TODO id를 입력하세요: ").strip()
    if not todo_id.isdigit():
        print("id는 숫자여야 합니다.")
        return

    path = f"{TODO_PATH}/{todo_id}"
    data = send_request("DELETE", path)
    print("응답:", data)


# ---------------------------------------------------------
# 간단한 메뉴 루프
# ---------------------------------------------------------

def print_menu():
    print("\n==============================")
    print("   TODO 클라이언트 메뉴")
    print("==============================")
    print("1. 전체 목록 조회 (GET /todo)")
    print("2. TODO 추가 (POST /todo)")
    print("3. 개별 조회 (GET /todo/{id})")
    print("4. TODO 수정 (PUT /todo/{id})")
    print("5. TODO 삭제 (DELETE /todo/{id})")
    print("0. 종료")
    print("==============================")


def main():
    while True:
        print_menu()
        choice = input("번호를 선택하세요: ").strip()

        if choice == "1":
            list_todos()
        elif choice == "2":
            create_todo()
        elif choice == "3":
            get_single_todo()
        elif choice == "4":
            update_todo()
        elif choice == "5":
            delete_todo()
        elif choice == "0":
            print("종료합니다.")
            break
        else:
            print("잘못된 선택입니다. 다시 입력하세요.")


if __name__ == "__main__":
    main()
