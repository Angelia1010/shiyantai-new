"""inference_service.py 的交互式测试脚本：先登录换取令牌，再循环提问。"""
import getpass

import requests

TASK_SERVICE_URL = "http://127.0.0.1:5001"
INFERENCE_URL = "http://127.0.0.1:8000/v1/chat"


def main() -> None:
    username = input("用户名 [admin]: ").strip() or "admin"
    password = getpass.getpass("密码: ")
    login = requests.post(f"{TASK_SERVICE_URL}/auth/login", json={"username": username, "password": password},
                          timeout=10)
    if login.status_code != 200:
        print("登录失败：", login.json().get("error"))
        return
    headers = {"X-Token": login.json()["token"]}

    print("已登录，输入问题开始对话（输入 exit 退出）")
    while True:
        prompt = input("\n问题: ").strip()
        if prompt.lower() in ("exit", "quit"):
            break
        if not prompt:
            continue
        try:
            resp = requests.post(INFERENCE_URL, json={"prompt": prompt, "max_tokens": 1024}, headers=headers,
                                 timeout=300)
        except requests.ConnectionError:
            print("连接失败：请确认 ollama serve 与 inference_service.py 都已启动")
            continue
        if resp.status_code == 200:
            print(resp.json()["response"])
            print(f"（耗时 {resp.elapsed.total_seconds():.1f}s）")
        else:
            print(f"请求失败 {resp.status_code}: {resp.text}")


if __name__ == "__main__":
    main()
