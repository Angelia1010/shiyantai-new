import requests
import json


class LLMService:
    def __init__(self):
        #self.config = settings.OLLAMA_CONFIG
        self.ollama_host = "127.0.0.1:11439"
        self.api_base_url = f"http://{self.ollama_host}/api"
        self.model = "DeepSeek-R1-Distill-Qwen-1.5B"
        self.time_out = 6000
    
    async def generate(self, prompt: str) -> str:
        response = requests.post(
            f"{self.api_base_url}/generate",
            json={
                "model": self.model,
                "prompt": prompt,
                "options": {
                    "num_predict": 100,
                    "temperature": 0.8
                }
            },
            timeout=self.time_out
        )
         
         # 尝试解析响应
        if response.status_code == 200:
            try:
                # 先尝试作为完整JSON解析
                data = response.json()
                #print(f"完整响应数据: {data}")
                
                if 'response' in data:
                    final_response = data['response']
                else:
                    final_response = str(data)  # 如果没有response字段，返回整个响应
                
                print(f"最终回复: {final_response}")
                return {"response": final_response}
                
            except json.JSONDecodeError:
                # 如果解析失败，尝试作为流式数据处理
                print("检测到流式响应")
                result = []
                for line in response.iter_lines():
                    if line:
                        try:
                            decoded = line.decode('utf-8')
                            data = json.loads(decoded)
                            #print(f"流数据块: {data}")
                            if 'response' in data:
                                result.append(data['response'])
                        except Exception as e:
                            print(f"解析流数据错误: {e}")
                
                final_response = ''.join(result)
                print(f"流式最终回复: {final_response}")
                return {"response": final_response}
        else:
            print(f"错误响应: {response.text}")
            return {"error": response.text}
        return {"response": final_response}
            
       