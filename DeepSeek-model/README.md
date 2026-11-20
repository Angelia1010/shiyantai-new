# 本地大模型（Ollama + DeepSeek-R1-Distill-Qwen-1.5B）

平台的大模型分析服务通过 Ollama 调用本地模型。部署步骤（详细截图见 `说明.docx`）：

1. 安装 Ollama Windows 版：<https://www.ollama.com/download/windows>
2. 准备模型文件 `DeepSeek-R1-Distill-Qwen-1.5B-Q6_K.gguf` 和 `Modelfile`（模型文件较大，不放在仓库里）。
3. 设置模型目录与监听地址。**只监听本机**，不要用 `0.0.0.0`，否则局域网内任何人都能调用模型：
   ```bat
   setx OLLAMA_MODELS "D:\models\DeepSeek"
   setx OLLAMA_HOST "127.0.0.1:11439"
   ```
   端口需与仓库根目录 `.env` 中的 `OLLAMA_URL` 一致（默认 `http://127.0.0.1:11439`）。
4. 加载模型：`ollama create DeepSeek-R1-Distill-Qwen-1.5B -f Modelfile`
5. 启动：`ollama serve`

`inference_service.py` 是一个可选的独立推理接口（默认端口 8000，需要登录令牌），平台本身不依赖它；
`test_service.py` 用来手工测试该接口。
