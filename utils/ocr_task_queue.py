# utils/ocr_task_queue.py
from dataclasses import dataclass
from typing import Optional, Callable, List
from enum import IntEnum
import numpy as np
import time

class OCRTaskPriority(IntEnum):
    """OCR任务优先级"""
    LOW = 0        # 批量自动识别
    NORMAL = 1     # 手动框选识别
    HIGH = 2      # 用户选中的特定区域

@dataclass
class OCRTask:
    """OCR任务"""
    task_id: str
    img: np.ndarray          # 图像区域
    roi: List[int]          # [x1, y1, x2, y2]
    page_key: str           # 页面对应key
    vertical: bool = False   # 是否竖排
    priority: int = OCRTaskPriority.NORMAL
    callback: Optional[Callable] = None
    created_at: float = 0
    retry_count: int = 0

class OCRTaskQueue:
    """OCR任务队列"""
    
    def __init__(self, max_workers: int = 2):
        self._queue: List[OCRTask] = []
        self._running: dict = {}
        self._max_workers = max_workers
        self._results: dict = {}  # task_id -> result
    
    def add_task(self, task: OCRTask) -> str:
        """添加任务"""
        task.created_at = time.time()
        self._queue.append(task)
        # 按优先级排序，高优先级在前
        self._queue.sort(key=lambda t: (t.priority, -t.created_at), reverse=True)
        return task.task_id
    
    def get_next_task(self) -> Optional[OCRTask]:
        """获取下一个待处理任务"""
        if len(self._running) >= self._max_workers:
            return None
        if self._queue:
            return self._queue.pop(0)
        return None
    
    def mark_running(self, task: OCRTask):
        self._running[task.task_id] = task
    
    def mark_finished(self, task_id: str, result=None):
        if task_id in self._running:
            del self._running[task_id]
        if result:
            self._results[task_id] = result
    
    def get_result(self, task_id: str) -> Optional[dict]:
        return self._results.get(task_id)
    
    def clear(self):
        self._queue.clear()
    
    @property
    def pending_count(self) -> int:
        return len(self._queue)
    
    @property
    def running_count(self) -> int:
        return len(self._running)
