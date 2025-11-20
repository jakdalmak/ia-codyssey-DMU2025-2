#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
FastAPI 기반 TODO 리스트 API (v2)

- todo_list: 메모리 상의 리스트로 TODO들을 관리
- APIRouter를 사용해 라우팅 구성
- 기본 기능 (예시)
  - 전체 조회   : GET  /todo
  - 추가        : POST /todo

- v2에서 추가된 기능
  - 개별 조회   : GET    /todo/{todo_id}         -> get_single_todo()
  - 수정        : PUT    /todo/{todo_id}         -> update_todo()
  - 삭제        : DELETE /todo/{todo_id}         -> delete_single_todo()
  - 수정용 모델 : TodoItem(BaseModel)
"""

from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException
from pydantic import BaseModel


# ---------------------------------------------------------
# Pydantic 모델 정의
# ---------------------------------------------------------

class TodoCreate(BaseModel):
    """
    새로운 TODO를 추가할 때 사용하는 모델
    (기본 todo.py에서 사용하던 Request Body라고 생각하면 됨)
    """
    title: str
    description: Optional[str] = None
    is_done: bool = False


class TodoItem(BaseModel):
    """
    과제 요구사항:
    - 수정 기능을 위한 모델을 따로 추가한다.
    - 해당 내용은 model.py에 추가한다.
    - 모델은 TodoItem이라는 이름으로 추가하고 BaseModel을 상속받아 구현한다.

    여기서는 편의상 todo_v2.py 안에 같이 두었지만,
    실제로는 model.py 로 옮겨서:

        from model import TodoItem

    형태로 import 해도 됨.

    수정(UPDATE)을 할 때 사용할 모델이므로
    부분 수정도 가능하도록(Optional)로 구성했다.
    """
    title: Optional[str] = None
    description: Optional[str] = None
    is_done: Optional[bool] = None


# ---------------------------------------------------------
# FastAPI 앱 & 라우터 설정
# ---------------------------------------------------------

app = FastAPI()
router = APIRouter()

# 메모리 상에 TODO들을 저장할 리스트
# 실제 DB는 아니고, 서버가 떠 있는 동안만 유지된다.
todo_list: List[dict] = []


# ---------------------------------------------------------
# 헬퍼 함수
# ---------------------------------------------------------

def _get_next_id() -> int:
    """
    todo_list 에서 다음에 사용할 id를 계산한다.
    리스트가 비어있으면 1부터 시작.
    """
    if not todo_list:
        return 1
    return todo_list[-1]["id"] + 1


def _find_todo_index_by_id(todo_id: int) -> int:
    """
    todo_id 값으로 todo_list 내의 인덱스를 찾는 헬퍼 함수.
    - 찾으면 해당 인덱스(int)
    - 못 찾으면 -1
    """
    for index, todo in enumerate(todo_list):
        if todo["id"] == todo_id:
            return index
    return -1


# ---------------------------------------------------------
# 기본 기능 (예: 전체 조회, 추가)
# (너의 todo.py에 이미 있던 내용일 가능성이 높은 부분)
# ---------------------------------------------------------

@router.get("/todo")
def get_todo_list():
    """
    TODO 전체 리스트 조회
    GET /todo
    """
    return todo_list


@router.post("/todo")
def add_todo(item: TodoCreate):
    """
    TODO 추가
    POST /todo

    Request Body 예시:
    {
      "title": "공부하기",
      "description": "FastAPI 과제 끝내기",
      "is_done": false
    }
    """
    new_id = _get_next_id()
    todo_dict = {
        "id": new_id,
        "title": item.title,
        "description": item.description,
        "is_done": item.is_done,
    }
    todo_list.append(todo_dict)
    return todo_dict


# ---------------------------------------------------------
# v2에서 요구된 추가 기능들
# 1) 개별 조회: get_single_todo()
# 2) 수정:     update_todo()
# 3) 삭제:     delete_single_todo()
# ---------------------------------------------------------

@router.get("/todo/{todo_id}")
def get_single_todo(todo_id: int):
    """
    개별 조회 기능
    - 함수 이름: get_single_todo()
    - HTTP 메서드: GET
    - 경로 매개변수로 id를 받는다.

    예)
    GET /todo/1
    """
    index = _find_todo_index_by_id(todo_id)
    if index == -1:
        raise HTTPException(status_code=404, detail="Todo not found")

    return todo_list[index]


@router.put("/todo/{todo_id}")
def update_todo(todo_id: int, item: TodoItem):
    """
    수정 기능
    - 함수 이름: update_todo()
    - HTTP 메서드: PUT
    - 경로 매개변수로 id를 받는다.
    - Request Body는 TodoItem(BaseModel)을 사용한다.
    """
    index = _find_todo_index_by_id(todo_id)
    if index == -1:
        raise HTTPException(status_code=404, detail="Todo not found")

    stored = todo_list[index]

    update_data = item.dict(exclude_unset=True)
    # 넘어온 값만 기존 dict에 덮어쓰기
    for key, value in update_data.items():
        stored[key] = value

    todo_list[index] = stored
    return stored


@router.delete("/todo/{todo_id}")
def delete_single_todo(todo_id: int):
    """
    삭제 기능
    - 함수 이름: delete_single_todo()
    - HTTP 메서드: DELETE
    - 경로 매개변수로 id를 받는다.

    """
    index = _find_todo_index_by_id(todo_id)
    if index == -1:
        raise HTTPException(status_code=404, detail="Todo not found")

    deleted = todo_list.pop(index)
    return deleted


# ---------------------------------------------------------
# 라우터를 FastAPI 앱에 등록
# ---------------------------------------------------------

app.include_router(router)


# ---------------------------------------------------------
# uvicorn으로 실행할 때를 위한 엔트리 포인트
# (python todo.py 로 실행 가능하게)
# ---------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    # uvicorn todo:app --reload
    uvicorn.run("todo:app", host="127.0.0.1", port=8000, reload=True)


"""
curl 테스트 예시

1) TODO 추가 (POST /todo)
---------------------------------
curl -X POST "http://127.0.0.1:8000/todo" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\": \"공부하기\", \"description\": \"FastAPI 과제\", \"is_done\": false}"

2) 전체 조회 (GET /todo)
---------------------------------
curl "http://127.0.0.1:8000/todo"

3) 개별 조회 (GET /todo/{id})
---------------------------------
curl "http://127.0.0.1:8000/todo/1"

4) 수정 (PUT /todo/{id})
---------------------------------
curl -X PUT "http://127.0.0.1:8000/todo/1" ^
  -H "Content-Type: application/json" ^
  -d "{\"title\": \"수정된 제목\", \"is_done\": true}"

5) 삭제 (DELETE /todo/{id})
---------------------------------
curl -X DELETE "http://127.0.0.1:8000/todo/1"
"""
