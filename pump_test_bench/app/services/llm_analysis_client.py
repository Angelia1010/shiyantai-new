import requests
import json
import os
from typing import Optional, Union
import tempfile
import time
import logging
import sys

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 获取父目录路径
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.append(parent_dir)
print(f"父目录路径: {parent_dir}")


class TDMSAnalysisClient:
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        初始化TDMS数据分析客户端
        
        参数:
            base_url: API服务的基础URL
        """
        self.base_url = base_url.rstrip('/')
        self.session_id = None
        self.last_analysis = None
    
    def analyze_file(
        self,
        file: Union[str, bytes, os.PathLike],
        session_id: Optional[str] = None,
        window_size: int = 10000,
        stride: int = 5000,
        show_progress: bool = True  # 保留参数但不使用
    ) -> dict:
        """
        分析TDMS文件
        
        参数:
            file: 可以是文件路径或文件对象
            session_id: 可选的会话ID
            window_size: 滑动窗口大小
            stride: 滑动步长
            show_progress: 不再使用，保留以兼容接口
            
        返回:
            包含完整分析结果的字典
        """
        # 确定文件来源类型
        if isinstance(file, (str, os.PathLike)):
            # 文件路径模式
            if not os.path.exists(file):
                raise FileNotFoundError(f"文件不存在: {file}")
            
            if not str(file).lower().endswith('.tdms'):
                raise ValueError("只支持TDMS格式文件")
            
            response = self._analyze_via_path(
                file_path=str(file),
                session_id=session_id,
                window_size=window_size,
                stride=stride,
                show_progress=show_progress
            )
        else:
            # 文件对象/上传模式
            response = self._analyze_via_upload(
                file=file,
                session_id=session_id,
                window_size=window_size,
                stride=stride,
                show_progress=show_progress
            )
        
        self.last_analysis = response
        self.session_id = response.get('session_id')
        return response
    
    def _analyze_via_path(
        self,
        file_path: str,
        session_id: Optional[str],
        window_size: int,
        stride: int,
        show_progress: bool
    ) -> dict:
        """通过文件路径分析"""
        url = f"{self.base_url}/analyze_json"
        payload = {
            "file_path": file_path,
            "session_id": session_id,
            "window_size": window_size,
            "stride": stride
        }
        
        return self._stream_process(
            url=url,
            json=payload,  # 使用json参数传递数据
            show_progress=show_progress,
            process_type="analysis"
        )
    
    def _analyze_via_upload(
        self,
        file: Union[bytes, tempfile._TemporaryFileWrapper],
        session_id: Optional[str],
        window_size: int,
        stride: int,
        show_progress: bool
    ) -> dict:
        """通过文件上传分析"""
        url = f"{self.base_url}/analyze"
        
        # 处理不同类型的文件输入
        if isinstance(file, bytes):
            # 字节数据
            file_obj = ('file', ('data.tdms', file, 'application/octet-stream'))
        else:
            # 文件对象
            file_obj = ('file', (os.path.basename(file.name), file, 'application/octet-stream'))
        
        data = {
            'session_id': session_id,
            'window_size': str(window_size),
            'stride': str(stride)
        }
        
        return self._stream_process(
            url=url,
            files={'file': file_obj},
            data=data,
            show_progress=show_progress,
            process_type="analysis"
        )
    
    def chat(
        self,
        question: str,
        window_idx: Optional[int] = None,
        session_id: Optional[str] = None,
        show_progress: bool = True  # 保留参数但不使用
    ) -> str:
        """
        与当前会话进行上下文对话
        
        参数:
            question: 问题文本
            window_idx: 相关窗口索引
            session_id: 会话ID (如果未提供则使用最后一次分析的会话ID)
            show_progress: 不再使用，保留以兼容接口
            
        返回:
            模型生成的回答
        """
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("没有可用的会话ID，请先分析文件")
        
        url = f"{self.base_url}/chat"
        payload = {
            "question": question,
            "session_id": sid,
            "window_idx": window_idx
        }
        print(url)
        response = self._stream_process(
            url=url,
            json=payload,
            show_progress=show_progress,
            process_type="chat"
        )
        
        return response.get('answer', '')
    
    def _stream_process(
        self,
        url: str,
        show_progress: bool,
        process_type: str,
        **request_args
    ) -> dict:
        """
        处理流式响应
        
        参数:
            url: 请求URL
            show_progress: 不再使用，保留以兼容接口
            process_type: 处理类型 ('analysis' 或 'chat')
            request_args: 传递给requests.post的参数
            
        返回:
            处理结果的字典
        """
        result = {
            'session_id': None,
            'summary': None,
            'critical_events': [],
            'stats': None,
            'answer': ''
        }

        with requests.post(url,**request_args, stream=True) as response:
            if response.status_code != 200:
                error = response.json().get('detail', '未知错误')
                raise RuntimeError(f"API请求失败: {error}")
            
            for line in response.iter_lines():
                if line:
                    event = json.loads(line.decode('utf-8'))
                    if event.get('event') == 'error':
                        raise RuntimeError(event.get('message', '未知错误'))
                    
                    # 处理分析结果
                    if process_type == "analysis":
                        if event.get('event') == 'start':
                            result['session_id'] = event.get('session_id')
                        elif event.get('event') == 'summary':
                            result['summary'] = event.get('data')
                        elif event.get('event') == 'critical_event':
                            result['critical_events'].append({
                                'window_idx': event.get('window_idx'),
                                'channels': event.get('channels'),
                                'z_scores': event.get('z_scores'),
                                'values': event.get('values')
                            })
                        elif event.get('event') == 'global_stats':
                            result['stats'] = event.get('data')
                    
                    # 处理对话结果
                    elif process_type == "chat":
                        print("88888888888888888888888888")
                        if event.get('event') == 'chat_response':
                            text = event.get('text', '')
                            if text:
                                result['answer'] += text
    
  
        
        '''
        try:
            with requests.post(url,**request_args, stream=True) as response:
                if response.status_code != 200:
                    error = response.json().get('detail', '未知错误')
                    raise RuntimeError(f"API请求失败: {error}")
                
                for line in response.iter_lines():
                    if line:
                        print("5555555555555555555")
                        event = json.loads(line.decode('utf-8'))
                        print("6666666666666666666666")
                        if event.get('event') == 'error':
                            raise RuntimeError(event.get('message', '未知错误'))
                        
                        # 处理分析结果
                        if process_type == "analysis":

                            print("77777777777777777777")
                            if event.get('event') == 'start':
                                result['session_id'] = event.get('session_id')
                            elif event.get('event') == 'summary':
                                result['summary'] = event.get('data')
                            elif event.get('event') == 'critical_event':
                                result['critical_events'].append({
                                    'window_idx': event.get('window_idx'),
                                    'channels': event.get('channels'),
                                    'z_scores': event.get('z_scores'),
                                    'values': event.get('values')
                                })
                            elif event.get('event') == 'global_stats':
                                result['stats'] = event.get('data')
                        
                        # 处理对话结果
                        elif process_type == "chat":
                            print("88888888888888888888888888")
                            if event.get('event') == 'chat_response':
                                text = event.get('text', '')
                                if text:
                                    result['answer'] += text
        
        except Exception as e:
            raise RuntimeError(f"处理流式响应失败: {str(e)}")
        '''
        return result
    
    def get_session_info(self, session_id: Optional[str] = None) -> dict:
        """
        获取会话信息
        
        参数:
            session_id: 会话ID (如果未提供则使用最后一次分析的会话ID)
            
        返回:
            会话信息字典
        """
        sid = session_id or self.session_id
        if not sid:
            raise ValueError("没有可用的会话ID，请先分析文件")
        
        url = f"{self.base_url}/session_info/{sid}"
        response = requests.get(url)
        
        if response.status_code != 200:
            error = response.json().get('detail', '未知错误')
            raise RuntimeError(f"获取会话信息失败: {error}")
        
        return response.json()
    
    def print_analysis_summary(self, analysis: Optional[dict] = None):
        """
        打印分析结果摘要
        
        参数:
            analysis: 分析结果字典 (如果未提供则使用最后一次分析的结果)
        """
        data = analysis or self.last_analysis
        if not data:
            print("没有可用的分析结果")
            return
        
        print("\n" + "="*50)
        print("分析摘要".center(40))
        print("="*50)
        print(data.get('summary', '无摘要信息'))
        
        events = data.get('critical_events', [])
        if events:
            print("\n" + "="*50)
            print(f"关键事件 ({len(events)}个)".center(40))
            print("="*50)
            for i, event in enumerate(events, 1):
                print(f"{i}. 窗口 {event['window_idx']}:")
                for name, score, value in zip(event['channels'], event['z_scores'], event['values']):
                    print(f"   {name}: 异常值 {value:.2f} (Z-score: {score:.1f})")
        
        stats = data.get('stats', {})
        if stats:
            print("\n" + "="*50)
            print("全局统计".center(40))
            print("="*50)
            print(f"平均值范围: {min(stats['global_mean']):.2f} 到 {max(stats['global_mean']):.2f}")
            print(f"标准差范围: {min(stats['global_std']):.2f} 到 {max(stats['global_std']):.2f}")
            print(f"最大值范围: {min(stats['max_values']):.2f} 到 {max(stats['max_values']):.2f}")
            print(f"最小值范围: {min(stats['min_values']):.2f} 到 {max(stats['min_values']):.2f}")

# 示例用法
if __name__ == "__main__":
    # 创建客户端实例
    client = TDMSAnalysisClient(base_url="http://localhost:8000")
    
    try:
        # 示例0: 直接调用大模型聊天（无需文件分析）
        print("\n示例0: 直接调用大模型聊天")
        # 这里传入一个测试用的session_id

        answer = client.chat(
            "你好",
            session_id="test_session_124"  # 传入测试session_id
        )
        print("\n问答结果:")
        print(answer)
        '''
        
        # 示例1: 通过文件路径分析
        print("示例1: 通过文件路径分析")
        data_dir = os.path.join(parent_dir, "test_data", "20241224-a")
        print(f"数据目录检查: {'存在' if os.path.exists(data_dir) else '不存在'} - {data_dir}")
    
        # 数据文件路径
        file_path = os.path.join(data_dir, "2412241453392020001（24A试验载荷谱-随动活塞磨损试验-11.5载荷谱）_.tdms")
        result = client.analyze_file(file_path)
        client.print_analysis_summary()
        '''
        '''
        # 示例2: 通过文件上传分析
        print("\n示例2: 通过文件上传分析")
        #with open(file_path, 'rb') as f:
        #    result = client.analyze_file(f)
        #client.print_analysis_summary()
        
        # 示例3: 上下文对话
        print("\n示例3: 上下文对话")
        answer = client.chat("请解释在窗口5附近出现的压力波动可能是什么原因？", window_idx=5)
        print("\n问答结果:")
        print(answer)
        
        # 示例4: 获取会话信息
        print("\n示例4: 获取会话信息")
        session_info = client.get_session_info()
        print(f"会话ID: {session_info['session_id']}")
        print(f"通道数量: {len(session_info['channel_names'])}")
        print(f"前5个通道: {', '.join(session_info['channel_names'][:5])}")
        '''
    except Exception as e:
        print(f"发生错误: {str(e)}")