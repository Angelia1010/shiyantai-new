from typing import List, Dict
import os
import sys
import logging
import redis
import pickle
import asyncio
import random

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 获取父目录路径
parent_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..'))
sys.path.append(parent_dir)
print(f"父目录路径: {parent_dir}")


class RedisCacheManager:
    def __init__(self, host: str = 'localhost', port: int = 6380, db: int = 0):
        """
        初始化Redis缓存管理器
        
        参数:
            host: Redis主机地址
            port: Redis端口
            db: Redis数据库编号
        """
        try:
            self.redis = redis.Redis(
                host=host, 
                port=port, 
                db=db, 
                decode_responses=False,
                socket_timeout=5,
                socket_connect_timeout=5
            )
            # 测试连接
            self.redis.ping()
            logger.info(f"成功连接到Redis服务器 {host}:{port} DB:{db}")
        except Exception as e:
            logger.error(f"连接Redis失败: {str(e)}")
            raise

    async def cache_window_result(self, result: Dict) -> bool:
        """
        缓存窗口分析结果
        
        参数:
            result: 窗口分析结果字典
            
        返回:
            是否缓存成功
        """
        try:
            session_id = result.get('session_id', 'default_session')
            window_idx = result['window_idx']
            
            # 使用哈希存储窗口结果
            key = f"{session_id}:windows"
            field = f"window_{window_idx}"
            
            # 序列化结果
            serialized = pickle.dumps(result)
            
            # 存储到Redis
            self.redis.hset(key, field, serialized)
            
            # 如果是关键窗口，添加到关键窗口集合
            if result.get('is_critical', False):
                crit_key = f"{session_id}:critical_windows"
                self.redis.sadd(crit_key, window_idx)
                
            return True
        except Exception as e:
            logger.error(f"缓存窗口结果失败: {str(e)}")
            return False
            
    async def get_context_windows(self, current_window_idx: int, 
                                session_id: str = 'default_session',
                                window_count: int = 3) -> List[Dict]:
        """
        获取上下文窗口（当前窗口前后的窗口）
        
        参数:
            current_window_idx: 当前窗口索引
            session_id: 会话ID
            window_count: 要获取的上下文窗口数量
            
        返回:
            上下文窗口结果列表
        """
        try:
            key = f"{session_id}:windows"
            
            # 计算要获取的窗口范围
            start_idx = max(1, current_window_idx - window_count)
            end_idx = current_window_idx + window_count
            
            # 获取这些窗口
            fields = [f"window_{i}" for i in range(start_idx, end_idx + 1) if i != current_window_idx]
            
            if not fields:
                return []
                
            # 批量获取
            results = self.redis.hmget(key, fields)
            
            # 反序列化
            return [pickle.loads(r) for r in results if r is not None]
        except Exception as e:
            logger.error(f"获取上下文窗口失败: {str(e)}")
            return []
            
    async def get_critical_windows(self, session_id: str = 'default_session') -> List[Dict]:
        """
        获取所有关键窗口
        
        参数:
            session_id: 会话ID
            
        返回:
            关键窗口结果列表
        """
        try:
            # 获取关键窗口索引集合
            crit_key = f"{session_id}:critical_windows"
            window_indices = self.redis.smembers(crit_key)
            
            if not window_indices:
                return []
                
            # 转换为整数
            indices = [int(idx) for idx in window_indices]
            
            # 获取这些窗口
            key = f"{session_id}:windows"
            fields = [f"window_{idx}" for idx in indices]
            
            results = self.redis.hmget(key, fields)
            
            # 反序列化
            return [pickle.loads(r) for r in results if r is not None]
        except Exception as e:
            logger.error(f"获取关键窗口失败: {str(e)}")
            return []
            
    async def clear_session(self, session_id: str) -> bool:
        """
        清除会话的所有缓存数据
        
        参数:
            session_id: 会话ID
            
        返回:
            是否清除成功
        """
        try:
            # 获取所有相关键
            keys = [
                f"{session_id}:windows",
                f"{session_id}:critical_windows"
            ]
            
            # 删除这些键
            self.redis.delete(*keys)
            logger.info(f"已清除会话 {session_id} 的缓存数据")
            return True
        except Exception as e:
            logger.error(f"清除会话缓存失败: {str(e)}")
            return False

async def main():
    # 初始化缓存管理器
    cache = RedisCacheManager(host='localhost', port=6380)
    
    # 测试会话ID
    session_id = f"test_session_{random.randint(1000, 9999)}"
    
    try:
        # 测试1: 缓存窗口结果
        print("\n=== 测试缓存窗口结果 ===")
        test_window = {
            'session_id': session_id,
            'window_idx': 1,
            'data': "这是第一个窗口的数据",
            'is_critical': True
        }
        
        success = await cache.cache_window_result(test_window)
        print(f"缓存结果: {'成功' if success else '失败'}")
        
        # 测试2: 获取上下文窗口
        print("\n=== 测试获取上下文窗口 ===")
        # 先缓存几个窗口
        for i in range(1, 6):
            await cache.cache_window_result({
                'session_id': session_id,
                'window_idx': i,
                'data': f"窗口{i}的数据",
                'is_critical': i % 2 == 0  # 偶数窗口设为关键窗口
            })
        
        context_windows = await cache.get_context_windows(
            current_window_idx=3,
            session_id=session_id,
            window_count=2
        )
        print(f"获取到的上下文窗口数: {len(context_windows)}")
        for window in context_windows:
            print(f"窗口{window['window_idx']}: {window['data']}")
        
        # 测试3: 获取关键窗口
        print("\n=== 测试获取关键窗口 ===")
        critical_windows = await cache.get_critical_windows(session_id)
        print(f"关键窗口数: {len(critical_windows)}")
        for window in critical_windows:
            print(f"关键窗口{window['window_idx']}: {window['data']}")
        
        # 测试4: 清除会话
        print("\n=== 测试清除会话 ===")
        success = await cache.clear_session(session_id)
        print(f"清除会话: {'成功' if success else '失败'}")
        
        # 验证是否已清除
        critical_windows = await cache.get_critical_windows(session_id)
        print(f"清除后关键窗口数: {len(critical_windows)}")
        
    except Exception as e:
        print(f"测试过程中出错: {e}")
    finally:
        # 清理测试数据
        await cache.clear_session(session_id)

if __name__ == "__main__":
    asyncio.run(main())