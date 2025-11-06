#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI + uvicorn + CSV 저장 기반 간단 TODO API

요구사항 요약
- 파일명: todo.py
- 리스트 객체: todo_list (List[Dict])
- APIRouter 로 2개 라우트
  - POST /todos -> add_todo(): Dict 입력 받아 CSV/메모리 저장, Dict 반환
  - GET  /todos -> retrieve_todo(): todo_list 반환(반드시 Dict로 감싸서)
- 보너스: 입력 Dict이 빈값이면 400 경고
"""

"""
사용한 명령어와 실행 방법 :

#0 venv를 github에 올리지는 않았습니다.
사유 : venv는 가상 환경이므로, 이를 올리게 된다면 구현된 python 환경 전체를 올리는 것과 다름없음.(용량 및 보안 등의 문제 가능성)
이 대신 개발자가 venv를 이용해 가상환경을 구현하면, 그 가상환경에 필요한 패키지 목록만을 제공하기위한
requirements.txt만 업로드하였음.  

#1 venv 가상 환경 구현 
python -m venv venv

#2 pip install 통해 가상환경에 필요 패키지 설치
#2-1 : 개발 중 설치했던 방식(venv를 구현하는 개발자 입장)
.\venv\Scripts\python.exe -m pip install --upgrade pip
.\venv\Scripts\python.exe -m pip install fastapi uvicorn

#2-2 : 본 프로젝트를 받아 동작시키고자 하는 개발자 입장에서의 설치 방식
# 아래 명령어를 이용하여, requirements.txt를 통해 필요 패키지들을 바로 받을 수 있습니다.
./venv/bin/python -m pip install -r requirements.txt        # macOS/Linux
.\venv\Scripts\python.exe -m pip install -r requirements.txt # Windows

# requirements.txt는 다음과 같이 구현하였습니다.
.\venv\Scripts\python.exe -m pip freeze > requirements.txt

#3 설치된 가상환경 내 uvicorn 기반으로 동작시키기.
.\venv\Scripts\python.exe -m uvicorn todo:app --reload

#4 curl 테스트 편리하게 하기위한 요청 내역 목록
curl -X POST "http://127.0.0.1:8000/todos" -H "Content-Type: application/json" -d "{\"content\":\"우유 사기\"}"
curl -X POST "http://127.0.0.1:8000/todos" -H "Content-Type: application/json" -d "{}"
curl "http://127.0.0.1:8000/todos"



"""

from typing import Any, Dict, List
from fastapi import FastAPI, APIRouter, HTTPException, status

# 전역 리스트 (요소 타입: Dict)
todo_list: List[Dict[str, Any]] = []

# 라우터 정의
router = APIRouter()


@router.post('/todos')
def add_todo(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    새로운 항목을 todo_list에 추가한다.
    - 입력: Dict(JSON)
    - 보너스: 빈 Dict 입력 시 400 경고
    - 반환: Dict(JSON)
    """
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='empty body is not allowed'
        )
    todo_list.append(payload)
    return {'ok': True, 'saved': payload}


@router.get('/todos')
def retrieve_todo() -> Dict[str, List[Dict[str, Any]]]:
    """
    현재 todo_list를 Dict로 감싸 반환한다.
    - 반환: {'todos': [...]}
    """
    return {'todos': todo_list}


# FastAPI 앱 및 라우터 연결
app = FastAPI(title='Todo API (in-memory)', version='1.0.0')
app.include_router(router)