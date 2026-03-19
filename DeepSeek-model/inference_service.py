# 安装依赖：pip install fastapi uvicorn requests
# -*- coding: utf-8 -*-
import os
import json
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional

app = FastAPI()
# 从环境变量读取配置
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "127.0.0.1:11439")
API_BASE_URL = f"http://{OLLAMA_HOST}/api"

class ChatRequest(BaseModel):
    prompt: str
    max_tokens: Optional[int] = 10
    temperature: Optional[float] = 0.7

@app.post("/v1/chat")
async def chat_completion(request: ChatRequest):
    """
    示例请求体：
    {
        "prompt": "如何制作蛋炒饭？",
        "max_tokens": 300,
        "temperature": 0.5
    }
    """
    try:
        # 调用Ollama原生API
        response = requests.post(
            f"{API_BASE_URL}/generate",
            json={
                "model": "DeepSeek-R1-Distill-Qwen-1.5B",
                "prompt": request.prompt,
                "options": {
                    "num_predict": request.max_tokens,
                    "temperature": request.temperature
                }
            },
            timeout=600
        )
        response.raise_for_status()
        
        # 处理流式响应（Ollama默认返回流数据）
        result = []
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')  # 字节转字符串
                data = json.loads(decoded_line)     # 解析 JSON
                if 'response' in data:
                    result.append(data['response'])
        final_response = ''.join(result)
        return {"response": final_response}
    
    except requests.exceptions.RequestException as e:
        raise HTTPException(status_code=500, detail=f"Ollama服务连接失败: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)