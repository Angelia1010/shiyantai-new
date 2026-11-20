"""大模型分析服务（默认端口 8999，前端代理前缀 /api/ai）。

接口一览（响应均为 NDJSON 流，每行一个 JSON 事件）：
    POST /analyze {path, file_name, session_id?, window_size?, stride?}
        事件：start → window × N → summary → done；出错时为 error
    POST /chat {question, session_id?}
        事件：answer → done；出错时为 error

支持 TDMS、Excel、TXT 数据文件（Excel/TXT 取全部数值列）。
大模型通过 Ollama 调用，地址与模型由 OLLAMA_URL / OLLAMA_MODEL 配置。

启动：在仓库根目录执行 ``python -m pump_test_bench.app.services.llm_service``
"""
import json
import logging
import uuid
from typing import AsyncIterator, Dict, Optional

import numpy as np
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from pump_test_bench.app.core.data_reader import TABLE_SUFFIXES, TDMS_SUFFIXES, read_table, read_tdms_matrix
from pump_test_bench.app.llm import analyzer
from pump_test_bench.app.llm.ollama_client import LLMError, OllamaClient
from pump_test_bench.app.llm.session_store import create_session_store
from shared.auth import verify_token
from shared.config import get_settings
from shared.logging_setup import setup_logging
from shared.paths import resolve_data_file

SERVICE_NAME = "llm_service"
logger = logging.getLogger(SERVICE_NAME)

app = FastAPI(title="试验台大模型分析服务")
_store = None


def store():
    global _store
    if _store is None:
        _store = create_session_store()
    return _store


def require_user(x_token: Optional[str] = Header(default=None)) -> str:
    user = verify_token(x_token)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


class AnalyzeRequest(BaseModel):
    path: str
    file_name: str
    session_id: Optional[str] = None
    window_size: int = Field(default=10000, gt=0)
    stride: int = Field(default=5000, gt=0)


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    session_id: Optional[str] = None


def _line(event: Dict) -> str:
    return json.dumps(event, ensure_ascii=False) + "\n"


def _load_matrix(path_str: str, file_name: str):
    path = resolve_data_file(path_str, file_name, TDMS_SUFFIXES + TABLE_SUFFIXES)
    if path.suffix.lower() in TDMS_SUFFIXES:
        return path, *read_tdms_matrix(path)
    _, df = read_table(path)
    numeric = df.select_dtypes(include="number")
    if numeric.empty:
        raise ValueError(f"文件 {path.name} 中没有数值列")
    return path, numeric.to_numpy(dtype=float), [str(c) for c in numeric.columns]


async def _stream(events: AsyncIterator[Dict], session_id: str) -> AsyncIterator[str]:
    try:
        async for event in events:
            yield _line({**event, "session_id": session_id})
        yield _line({"event": "done", "session_id": session_id})
    except (ValueError, LLMError) as exc:
        yield _line({"event": "error", "message": str(exc)})
    except Exception:
        logger.exception("大模型分析失败")
        yield _line({"event": "error", "message": "分析过程出现内部错误，请查看服务日志"})


@app.get("/health")
def health():
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/analyze")
def analyze(req: AnalyzeRequest, user: str = Depends(require_user)):
    session_id = req.session_id or uuid.uuid4().hex
    try:
        path, data, names = _load_matrix(req.path, req.file_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    async def events():
        session = store().get(session_id) or {}
        async for event in analyzer.analyze(OllamaClient(), np.asarray(data), names, path.name,
                                            req.window_size, req.stride, get_settings().llm_max_windows, session):
            yield event
        store().save(session_id, session)

    logger.info("用户 %s 开始分析 %s（会话 %s）", user, path, session_id)
    return StreamingResponse(_stream(events(), session_id), media_type="application/x-ndjson")


@app.post("/chat")
def chat(req: ChatRequest, user: str = Depends(require_user)):
    session_id = req.session_id or uuid.uuid4().hex

    async def events():
        session = store().get(session_id) or {}
        reply = await analyzer.answer(OllamaClient(), req.question, session)
        store().save(session_id, session)
        yield {"event": "answer", "text": reply}

    return StreamingResponse(_stream(events(), session_id), media_type="application/x-ndjson")


def main() -> None:
    import uvicorn

    settings = get_settings()
    setup_logging(SERVICE_NAME)
    logger.info("大模型分析服务启动：http://%s:%s，模型：%s @ %s", settings.bind_host, settings.llm_service_port,
                settings.ollama_model, settings.ollama_url)
    uvicorn.run(app, host=settings.bind_host, port=settings.llm_service_port, log_level="info")


if __name__ == "__main__":
    main()
