from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from fastapi.responses import StreamingResponse
from typing import Optional
from pydantic import BaseModel
from contextlib import asynccontextmanager
import os
import sys
import logging
from datetime import datetime
import json
import tempfile

# 获取父目录路径
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)
print(f"父目录路径: {parent_dir}")
from core.analysis.llm.llm_service import LLMService
from core.diagonis_data_process import FaultDataProcessor
from core.analysis.llm.diagnosis_llm import LargeDataAnalyzer

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 全局变量存储分析器实例
_analyzer = None

# 生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动逻辑
    logger.info("液压系统数据分析服务启动")
    yield
    # 关闭逻辑
    logger.info("液压系统数据分析服务关闭")
    if _analyzer and hasattr(_analyzer, 'cache'):
        await _analyzer.cache.close()

app = FastAPI(
    title="液压系统数据分析API",
    description="提供液压系统数据分析和大模型对话服务，支持TDMS文件上传或路径指定",
    version="1.0.1",
    lifespan=lifespan
)

class FileInput(BaseModel):
    file_path: Optional[str] = None
    session_id: Optional[str] = None
    window_size: int = 10000
    stride: int = 5000
    file: Optional[str] = None

class ChatInput(BaseModel):
    question: str
    session_id: Optional[str] = None
    window_idx: Optional[int] = None

@app.post("/analyze")
async def analyze_data(
    file: Optional[UploadFile] = File(None),
    file_input: Optional[FileInput] = Body(None),
    question: Optional[str] = Form(None)
):
    """
    数据分析接口
    
    参数:
    - file: 上传的TDMS文件 (与file_input二选一)
    - file_input: JSON格式的输入 (与file二选一)
      - file_path: TDMS文件路径
      - session_id: 会话ID (可选)
      - window_size: 滑动窗口大小 (默认10000)
      - stride: 滑动步长 (默认5000)
    - question: 问题文本 (可选，当没有文件时作为对话问题)
    
    返回:
    - 流式响应，包含分析结果或对话回答
    """
    if file is None and file_input is None and question is None:
        raise HTTPException(status_code=400, detail="必须提供文件或问题")
    
    if file is not None or file_input is not None:
        if file and file_input:
            raise HTTPException(status_code=400, detail="不能同时上传文件和提供文件路径")
        
        if file_input:
            session_id = file_input.session_id
            window_size = file_input.window_size
            stride = file_input.stride
            file_path = file_input.file_path
        else:
            session_id = None
            window_size = 10000
            stride = 5000
            file_path = None
        
        return StreamingResponse(
            stream_analysis(file, file_path, session_id, window_size, stride),
            media_type="text/event-stream"
        )
    else:
        return StreamingResponse(
            stream_chat_response(question, None),
            media_type="text/event-stream"
        )
        
@app.post("/chat")
async def chat_with_context(chat_input: ChatInput):
    """
    上下文对话接口
    """
    return StreamingResponse(
        stream_chat_response(chat_input.question, chat_input.session_id),
        media_type="text/event-stream"
    )

@app.post("/analyze_json")
async def analyze_data_json(file_input: FileInput):
    """JSON格式的数据分析接口（支持完整流式输出）"""
    return StreamingResponse(
        stream_analysis(
            file=None,
            file_path=file_input.file_path,
            session_id=file_input.session_id,
            window_size=file_input.window_size,
            stride=file_input.stride
        ),
        media_type="text/event-stream"
    )

async def stream_analysis(
    file: Optional[UploadFile],
    file_path: Optional[str],
    session_id: Optional[str],
    window_size: int,
    stride: int
):
    global _analyzer
    tdms_path = None
    
    try:
        # 验证输入参数
        if not any([file, file_path]):
            yield json.dumps({
                "event": "error",
                "code": 400,
                "message": "需要提供文件或文件路径"
            }) + "\n\n"
            return

        # 文件路径验证
        if file_path:
            if not os.path.exists(file_path):
                yield json.dumps({
                    "event": "error",
                    "code": 400,
                    "message": "文件路径不存在"
                }) + "\n\n"
                return
            if not file_path.lower().endswith('.tdms'):
                yield json.dumps({
                    "event": "error",
                    "code": 400,
                    "message": "仅支持TDMS格式文件"
                }) + "\n\n"
                return
            tdms_path = file_path

        # 文件上传处理
        if file:
            contents = await file.read()
            with tempfile.NamedTemporaryFile(suffix=".tdms", delete=False) as tmp:
                tmp.write(contents)
                tdms_path = tmp.name

        # 数据预处理
        processor = FaultDataProcessor(tdms_path)
        raw_data, columns = processor.get_fault_data(group_channel_list=[])

        # 初始化分析器
        _analyzer = LargeDataAnalyzer(
            llm_service=LLMService(),
            channel_names=columns,
            window_size=window_size,
            stride=stride,
            session_id=session_id or f"session_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        
        async for window_result in _analyzer.stream_analyze(raw_data):
            json_str = window_result["analysis"]
            yield json_str
          
        # 最终汇总
        final_report = await _analyzer.generate_final_report()
        yield final_report["summary"]
    except Exception as e:
        error_event = {
            "event": "error",
            "code": 500,
            "message": f"分析过程中发生错误: {str(e)}"
        }
        yield json.dumps(error_event) + "\n\n"
    finally:
        # 资源清理
        if tdms_path and os.path.exists(tdms_path):
            try:
                os.unlink(tdms_path)
            except Exception as e:
                logger.error(f"临时文件清理失败: {str(e)}")

async def stream_chat_response(question: str, session_id: Optional[str]):
    try:
        global _analyzer
        _analyzer = LargeDataAnalyzer(
            llm_service=LLMService(),
            channel_names=[],
            window_size=100,
            stride=50,
            session_id=session_id or f"session_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        )
        
        window_idx = 100
        answer = await _analyzer.query_with_context(question, window_idx)
        
        if not isinstance(answer, dict) or 'response' not in answer:
            raise ValueError("Invalid response format from analyzer")

        # 获取response内容并确保是字符串
        response_text = str(answer['response']) if answer['response'] is not None else ""
        
        # 分块流式返回
        chunk_size = 100
        for i in range(0, len(response_text), chunk_size):
            yield response_text[i:i+chunk_size]
    except Exception as e:
        logger.error(f"对话失败: {str(e)}", exc_info=True)
        yield json.dumps({
            "event": "error",
            "message": f"对话失败: {str(e)}"
        }) + "\n\n"


@app.get("/session_info/{session_id}")
async def get_session_info(session_id: str):
    if _analyzer is None or _analyzer.session_id != session_id:
        raise HTTPException(status_code=404, detail="会话不存在或已过期")
    
    return {
        "session_id": session_id,
        "channel_names": _analyzer.channel_names,
        "window_size": _analyzer.window_size,
        "stride": _analyzer.stride,
        "created_at": datetime.now().isoformat(),
        "file_source": "unknown"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "llm_analysis_server:app",  # 模块名:FastAPI实例名
        host="0.0.0.0",             # 监听所有网络接口
        port=8999,                  # 端口号
        reload=True,                # 开发时启用热重载
        workers=1,                  # 生产环境可以增加worker数量
        log_level="info"            # 日志级别
    )