# utils/inpaint_task_queue.py
from dataclasses import dataclass
from typing import Optional, Callable
from enum import IntEnum
import numpy as np

class TaskPriority(IntEnum):
    """任务优先级"""
    LOW = 0       # 批量处理
    NORMAL = 1    # 普通
    HIGH = 2      # 用户交互

@dataclass
class InpaintTask:
    """图像修复任务"""
    task_id: str
    img: np.ndarray
    mask: np.ndarray
    inpaint_rect: Optional[List[int]] = None
    img_key: Optional[str] = None
    priority: TaskPriority = TaskPriority.NORMAL
    callback: Optional[Callable] = None
    # 元数据
    created_at: float = 0
    user_data: dict = None

class InpaintTaskQueue:
    """线程安全的任务队列"""
    
    def __init__(self, max_workers: int = 2):
        self._queue = []
        self._running = {}  # task_id -> InpaintTask
        self._max_workers = max_workers
    
    def add_task(self, task: InpaintTask) -> str:
        """添加任务（自动排序优先级）"""
        self._queue.append(task)
        self._queue.sort(key=lambda t: t.priority, reverse=True)
        return task.task_id
    
    def get_next_task(self) -> Optional[InpaintTask]:
        """获取下一个待执行任务"""
        if len(self._running) >= self._max_workers:
            return None
        if self._queue:
            return self._queue.pop(0)
        return None
    
    def mark_running(self, task: InpaintTask):
        self._running[task.task_id] = task
    
    def mark_finished(self, task_id: str):
        if task_id in self._running:
            del self._running[task_id]
    
    def clear(self):
        """清空队列（用于取消操作）"""
        self._queue.clear()
    
    def size(self) -> int:
        return len(self._queue) + len(self._running)
