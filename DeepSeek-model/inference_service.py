"""大模型调用的独立 HTTP 接口（可选，平台本身不依赖它）。

平台的大模型分析服务（pump_test_bench/app/services/llm_service.py）直接调用 Ollama；
本服务供其它程序或手工测试（test_service.py）使用，同样需要登录令牌。

启动：在仓库根目录执行 ``python DeepSeek-model/inference_service.py``。
端口由环境变量 INFERENCE_SERVICE_PORT 配置，默认 8000。
"""
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 目录名含连字符，只能这样引用仓库内模块

from fastapi import Depends, FastAPI, Header, HTTPException  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from pump_test_bench.app.llm.ollama_client import LLMError, OllamaClient  # noqa: E402
from shared.auth import verify_token  # noqa: E402
from shared.config import get_settings  # noqa: E402

app = FastAPI(title="大模型推理接口")


class ChatRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=8000)
    max_tokens: int = Field(default=512, gt=0, le=8192)
    temperature: float = Field(default=0.7, ge=0, le=2)


def require_user(x_token: Optional[str] = Header(default=None)) -> str:
    user = verify_token(x_token)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return user


@app.post("/v1/chat")
async def chat(req: ChatRequest, _user: str = Depends(require_user)):
    try:
        text = await OllamaClient().generate(req.prompt, max_tokens=req.max_tokens, temperature=req.temperature)
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"response": text}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=get_settings().bind_host, port=int(os.environ.get("INFERENCE_SERVICE_PORT", "8000")))
