# -*- coding: utf-8 -*-
import json
import requests
from rich.console import Console
from rich.syntax import Syntax
from rich.prompt import Prompt
import sys
import os

# API配置
API_URL = "http://127.0.0.1:8000/v1/chat"

def test_chat_api():
    """交互式测试聊天API"""
    print("[bold green]Ollama API测试客户端[/bold green] (输入 'exit' 退出)")

    while True:
        try:
            # 获取用户输入
            prompt = Prompt.ask("\n[bold cyan]请输入问题[/bold cyan]")
            if prompt.lower() in ['exit', 'quit']:
                break

            # 构建请求参数
            payload = {
                "prompt": prompt,
                "max_tokens": 1024,
                "temperature": 0.8
            }

            # 发送请求
            print("[bold yellow]正在生成响应...")
            response = requests.post(
                API_URL,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=300
            )

            # 处理响应
            if response.status_code == 200:
                result = response.json()
                print("\n[bold green]✓ 响应成功:[/bold green]")

                # 格式化显示代码块
                if "```" in result["response"]:
                    code_blocks = result["response"].split("```")
                    for i, block in enumerate(code_blocks):
                        if i % 2 == 1:  # 代码块
                            lang = block.split("\n")[0] or "text"
                            code = "\n".join(block.split("\n")[1:])
                            print(Syntax(code, lang, theme="monokai"))
                        else:
                            print(block)
                else:
                    # 确保使用 UTF-8 编码显示输出
                    #print("hahahahha")
                    print(result["response"])

                # 显示性能信息
                print(f"\n[dim]状态码: {response.status_code}  响应时间: {response.elapsed.total_seconds():.2f}s[/dim]")

            else:
                print(f"[bold red]✗ 请求失败 (状态码 {response.status_code})[/bold red]")
                print(f"错误详情: {response.text}")

        except requests.exceptions.ConnectionError:
            print("[bold red]✗ 连接失败：请检查以下项目：[/bold red]")
            print("1. Ollama服务是否运行（ollama serve）")
            print("2. Python API服务是否运行（python app.py）")
            print("3. 防火墙是否放行端口8000和11435")

        except requests.exceptions.Timeout:
            print("[bold red]✗ 请求超时：尝试调整max_tokens参数或检查服务器性能[/bold red]")

        except KeyboardInterrupt:
            print("\n[bold yellow]⚠ 用户中断操作[/bold yellow]")
            break

        except Exception as e:
            print(f"[bold red]✗ 未预期的错误: {str(e)}[/bold red]")

if __name__ == "__main__":
    test_chat_api()
    print("\n[bold blue]测试结束，感谢使用！[/bold blue]")
