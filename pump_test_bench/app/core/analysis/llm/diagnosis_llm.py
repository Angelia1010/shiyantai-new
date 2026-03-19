import numpy as np
from tqdm import tqdm
from typing import List, Dict, Any, Optional, AsyncGenerator
import json
from collections import defaultdict
import os
import sys
from datetime import datetime
import logging
import asyncio

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 获取父目录路径
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.append(parent_dir)
print(f"父目录路径: {parent_dir}")

from core.analysis.llm.llm_service import LLMService
from core.diagonis_data_process import FaultDataProcessor
from services.redis_server import RedisCacheManager

class LargeDataAnalyzer:
    def __init__(self, llm_service: LLMService, channel_names: List[str], 
                 window_size: int = 100, stride: int = 50,
                 redis_host: str = "localhost", redis_port: int = 6380, redis_db: int = 0,
                 session_id: Optional[str] = None):
        """
        初始化大数据分析器
        
        参数:
            llm_service: LLMService实例
            channel_names: 各通道名称列表
            window_size: 滑动窗口大小
            stride: 滑动步长
            redis_host: Redis主机地址
            redis_port: Redis端口
            redis_db: Redis数据库编号
            session_id: 会话ID，用于上下文对话
        """
        self.llm = llm_service
        self.channel_names = channel_names
        self.window_size = window_size
        self.stride = stride
        self.window_results = []
        self.session_id = session_id or f"session_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.cache = RedisCacheManager(host=redis_host, port=redis_port, db=redis_db)
        self.dialogue_context = []
        
    async def analyze(self, data: np.ndarray) -> Dict[str, Any]:
        """
        执行完整分析流程并返回汇总结果
        
        参数:
            data: 输入数据矩阵 (n_samples, n_channels)
            
        返回:
            包含完整分析结果的字典
        """
        if not isinstance(data, np.ndarray):
            raise ValueError("输入数据必须是numpy数组")
            
        window_results = []
        async for result in self._sliding_window_analysis(data):
            window_results.append(result)
            
        summary = await self._summarize_results(window_results)
        critical_events = self._identify_critical_events(window_results)
        
        return {
            "session_id": self.session_id,
            "window_analyses": window_results,
            "summary": summary,
            "critical_events": critical_events,
            "stats": self._compute_global_stats(window_results)
        }
    
    async def stream_analyze(self, data: np.ndarray) -> AsyncGenerator[Dict, None]:
        """
        异步生成器，实时生成每个窗口的分析结果
        
        参数:
            data: 输入数据矩阵
            
        生成:
            每个窗口的分析结果字典
        """
        async for result in self._sliding_window_analysis(data):
            yield result
    
    async def _sliding_window_analysis(self, data: np.ndarray) -> AsyncGenerator[Dict, None]:
        """执行滑动窗口分析并异步生成结果"""
        n_samples = data.shape[0]
        
        total_windows = (n_samples - self.window_size) // self.stride + 1
        progress_bar = tqdm(total=total_windows, desc="Analyzing data windows")
        
        try:
            for i in range(0, n_samples - self.window_size + 1, self.stride):
                window_data = data[i:i+self.window_size]
                window_idx = i//self.stride + 1
                result = await self._analyze_window(window_data, window_idx)
                
                result['session_id'] = self.session_id
                await self.cache.cache_window_result(result)
                self.window_results.append(result)
                progress_bar.update(1)
                yield result
        finally:
            progress_bar.close()
    
    async def _analyze_window(self, window_data: np.ndarray, window_idx: int) -> Dict:
        """分析单个数据窗口"""
        stats = {
            "mean": np.nanmean(window_data, axis=0).tolist(),
            "std": np.nanstd(window_data, axis=0).tolist(),
            "max": np.nanmax(window_data, axis=0).tolist(),
            "min": np.nanmin(window_data, axis=0).tolist(),
            "start_idx": (window_idx - 1) * self.stride,
            "end_idx": (window_idx - 1) * self.stride + self.window_size,
            "stride": self.stride
        }
        
        try:
            context_windows = await self.cache.get_context_windows(window_idx, self.session_id)
            prompt = self._build_window_prompt(stats, window_idx, context_windows)
            llm_response = await self.llm.generate(prompt)
            
            analysis_text = str(llm_response)
            if isinstance(llm_response, dict):
                analysis_text = llm_response.get('response', analysis_text)
                
            return {
                "window_idx": window_idx,
                "stats": stats,
                "analysis": analysis_text[:5000],
                "raw_response": llm_response,
                "error": None,
                "channel_names": self.channel_names,
                "is_critical": False
            }
        except Exception as e:
            logger.error(f"窗口{window_idx}分析失败: {str(e)}")
            return {
                "window_idx": window_idx,
                "stats": stats,
                "analysis": None,
                "error": str(e),
                "channel_names": self.channel_names,
                "is_critical": False
            }
    
    def _build_window_prompt(self, stats: Dict, window_idx: int, 
                       context_windows: List[Dict] = None) -> str:
        """构建窗口分析提示"""
        top_channels = sorted(
            zip(self.channel_names, stats["mean"]), 
            key=lambda x: abs(x[1]), 
            reverse=True
        )[:5]
        
        prompt = f"""作为试验台故障诊断专家，请分析以下窗口数据（窗口{window_idx}，位置:{stats['start_idx']}-{stats['end_idx']}）：

通道列表：{', '.join(self.channel_names)}

窗口统计：
- 平均值（前5显著）：
{'\\n'.join([f'  {name}: {value:.4f}' for name, value in top_channels])}
- 标准差范围：{min(stats['std']):.4f} 到 {max(stats['std']):.4f}
- 极值范围：{min(stats['min']):.4f} 到 {max(stats['max']):.4f}"""
        
        if context_windows:
            prompt += "\n\n上下文窗口信息："
            for ctx in context_windows:
                if ctx.get("window_idx") == window_idx:
                    continue
                    
                ctx_stats = ctx.get("stats", {})
                ctx_top = sorted(
                    zip(self.channel_names, ctx_stats.get("mean", [])), 
                    key=lambda x: abs(x[1]), 
                    reverse=True
                )[:3]
                
                ctx_start = ctx_stats.get("start_idx", "未知")
                ctx_end = ctx_stats.get("end_idx", "未知")
                
                prompt += f"\n- 窗口{ctx.get('window_idx', '未知')} ({ctx_start}-{ctx_end}):"
                prompt += f"\n  主要通道: {', '.join([f'{name}({value:.2f})' for name, value in ctx_top])}"
                
                ctx_analysis = ctx.get("analysis", "")
                if ctx_analysis:
                    prompt += f"\n  分析摘要: {ctx_analysis[:100]}..."
                else:
                    prompt += "\n  分析摘要: 无可用分析结果"
        
        prompt += """

请：
1. 识别异常通道（如有）
2. 评估窗口内系统状态
3. 标记需要关注的趋势
4. 与上下文窗口比较变化
5. 用中文回答，保持专业但简洁"""

        return prompt

    async def _summarize_results(self, window_results: List[Dict]) -> str:
        """汇总各窗口分析结果"""
        valid_results = [r for r in window_results if r.get("analysis")]
        
        if not valid_results:
            return "无有效分析结果可供汇总"
            
        all_means = np.array([r["stats"]["mean"] for r in valid_results])
        global_stats = {
            "mean": np.nanmean(all_means, axis=0).tolist(),
            "std": np.nanstd(all_means, axis=0).tolist()
        }
        
        critical_events = await self.cache.get_critical_windows(self.session_id)
        
        prompt = f"""作为首席液压系统分析师，请汇总{len(window_results)}个窗口的分析结果：

数据集概况：
- 会话ID: {self.session_id}
- 总通道数：{len(self.channel_names)}
- 主要通道：{', '.join(self.channel_names[:5])}等
- 数据范围：{window_results[0]['stats']['start_idx']} 到 {window_results[-1]['stats']['end_idx']}

全局统计：
- 各通道平均值范围：{np.nanmin(all_means):.2f} 到 {np.nanmax(all_means):.2f}
- 标准差范围：{np.nanmin(global_stats['std']):.2f} 到 {np.nanmax(global_stats['std']):.2f}

关键事件({len(critical_events)}个):"""
        
        for i, event in enumerate(critical_events[:3], 1):
            prompt += f"\n{i}. 窗口{event['window_idx']}: {event.get('analysis', '无分析内容')[:100]}..."
        
        prompt += """

请提供：
1. 系统整体健康评估（优良中差）
2. 最需要关注的3个问题
3. 优先级排序的维护建议
4. 与历史类似会话的比较（如有）
5. 用中文回答，分条目列出，保持专业简洁"""
        
        try:
            return await self.llm.generate(prompt)
        except Exception as e:
            logger.error(f"汇总结果失败: {str(e)}")
            return f"无法生成汇总报告: {str(e)}"
    
    def _identify_critical_events(self, window_results: List[Dict]) -> List[Dict]:
        """识别关键事件窗口"""
        critical_windows = []
        threshold = 3
        
        for result in window_results:
            if result.get("error") or not result.get("stats"):
                continue
                
            means = np.array(result["stats"]["mean"])
            stds = np.array(result["stats"]["std"])
            z_scores = np.abs((means - np.nanmean(means)) / (stds + 1e-6))
            anomalies = np.where(z_scores > threshold)[0]
            
            if anomalies.size > 0:
                critical_windows.append({
                    "window_idx": result["window_idx"],
                    "channels": [self.channel_names[i] for i in anomalies],
                    "z_scores": [z_scores[i] for i in anomalies],
                    "values": [means[i] for i in anomalies],
                    "analysis": result.get("analysis", "")
                })
                result["is_critical"] = True
                
        return critical_windows
    
    def _compute_global_stats(self, window_results: List[Dict]) -> Dict:
        """计算全局统计信息"""
        valid_results = [r for r in window_results if not r.get("error")]
        
        if not valid_results:
            return {
                "global_mean": [0] * len(self.channel_names),
                "global_std": [0] * len(self.channel_names),
                "max_values": [0] * len(self.channel_names),
                "min_values": [0] * len(self.channel_names)
            }
            
        all_means = np.array([r["stats"]["mean"] for r in valid_results])
        
        return {
            "global_mean": np.nanmean(all_means, axis=0).tolist(),
            "global_std": np.nanstd(all_means, axis=0).tolist(),
            "max_values": np.nanmax(all_means, axis=0).tolist(),
            "min_values": np.nanmin(all_means, axis=0).tolist()
        }
    
    async def query_with_context(self, question: str, window_idx: Optional[int] = None) -> str:
        """
        基于上下文的问答
        
        参数:
            question: 用户问题
            window_idx: 相关窗口索引（可选）
            
        返回:
            回答内容
        """
        self.dialogue_context.append({"role": "user", "content": question})
        
        context = ""
        if window_idx is not None:
            context_windows = await self.cache.get_context_windows(window_idx, self.session_id)
            if context_windows:
                context = "\n\n相关窗口上下文："
                for ctx in context_windows:
                    context += f"\n- 窗口{ctx.get('window_idx', '未知')}: {ctx.get('analysis', '无分析内容')[:200]}..."
        
        prompt = f"""作为试验台故障诊断系统专家，当问及你是谁是，直接回复是试验台故障诊断专家，问及可以做什么时，直接回答我可以做运维排障、数据分析、故障诊断等，请回答以下问题：

用户问题: {question}"""
        
        try:
            response = await self.llm.generate(prompt)
            self.dialogue_context.append({"role": "assistant", "content": response})
            return response
        except Exception as e:
            logger.error(f"查询失败: {str(e)}")
            return f"无法回答问题: {str(e)}"


async def main():
    # 设置数据目录路径
    data_dir = os.path.join(parent_dir, "test_data", "20241224-a")
    print(f"数据目录检查: {'存在' if os.path.exists(data_dir) else '不存在'} - {data_dir}")
    
    # 数据文件路径
    data_file = os.path.join(data_dir, "2412241453392020001（24A试验载荷谱-随动活塞磨损试验-11.5载荷谱）_.tdms")
    
    # 使用FaultDataProcessor读取数据
    processor = FaultDataProcessor(data_file)
    raw_data, columns = processor.get_fault_data(group_channel_list=[])
    print(f"加载数据完成，形状: {raw_data.shape}")

    # 初始化LLM服务
    llm_service = LLMService()

    # 创建分析器实例
    analyzer = LargeDataAnalyzer(
        llm_service=llm_service,
        channel_names=columns,
        window_size=10000,
        stride=5000,
        redis_host="localhost",
        redis_port=6380,
        redis_db=0,
        session_id="test_session_123"
    )

    # 实时处理任务
    async def realtime_handler():
        async for result in analyzer.stream_analyze(raw_data):
            print(f"\n[实时更新] 窗口 {result['window_idx']} 分析完成")
            print(f"时间范围: {result['stats']['start_idx']}-{result['stats']['end_idx']}")
            print(f"关键分析: {result['analysis'][:150]}...")
            if result['is_critical']:
                print("⚠️ 检测到关键事件 ⚠️")

    # 完整分析任务
    async def full_analysis():
        final_result = await analyzer.analyze(raw_data)
        print("\n" + "="*50 + "\n最终分析报告:\n" + "="*50)
        print(final_result["summary"])
        print("\n关键事件统计:", len(final_result["critical_events"]))

    # 并行执行任务
    await asyncio.gather(
        realtime_handler(),
        full_analysis()
    )

if __name__ == "__main__":
    asyncio.run(main())