# ui/inpaint_worker.py
from qtpy.QtCore import QThread, Signal, QObject, QMutex, QWaitCondition
from typing import Optional, List
import numpy as np

from utils.inpaint_task_queue import InpaintTask, InpaintTaskQueue, TaskPriority
from utils.logger import logger as LOGGER

class InpaintWorker(QObject):
    """异步图像修复工作器"""
    
    # 信号定义
    task_started = Signal(str)                    # task_id
    task_progress = Signal(str, int)               # task_id, progress (0-100)
    task_finished = Signal(dict)                   # inpaint_dict
    task_failed = Signal(str, str)                 # task_id, error_msg
    queue_empty = Signal()                          # 所有任务完成
    
    def __init__(self, inpainter, parent=None):
        super().__init__(parent)
        self.inpainter = inpainter
        self._task_queue = InpaintTaskQueue(max_workers=2)
        self._current_task: Optional[InpaintTask] = None
        self._running = False
        self._mutex = QMutex()
    
    def add_task(self, 
                 img: np.ndarray, 
                 mask: np.ndarray,
                 inpaint_rect=None,
                 img_key=None,
                 priority=TaskPriority.NORMAL,
                 callback=None) -> str:
        """添加新任务"""
        import uuid
        task_id = str(uuid.uuid4())[:8]
        
        task = InpaintTask(
            task_id=task_id,
            img=img,
            mask=mask,
            inpaint_rect=inpaint_rect,
            img_key=img_key,
            priority=priority,
            callback=callback
        )
        
        self._task_queue.add_task(task)
        LOGGER.info(f"[InpaintWorker] Added task {task_id}, queue size: {self._task_queue.size()}")
        
        # 如果未运行，启动处理
        if not self._running:
            self._start_processing()
        
        return task_id
    
    def _start_processing(self):
        """启动任务处理"""
        self._running = True
        # 建议使用 QThreadPool 或单独线程处理
        # 这里触发实际的 inpaint 调用
    
    def cancel_all(self):
        """取消所有待处理任务"""
        self._task_queue.clear()
        LOGGER.info("[InpaintWorker] All pending tasks cancelled")
    
    def get_queue_size(self) -> int:
        return self._task_queue.size()

# 扩展功能：批量 inpaint
class BatchInpaintManager:
    """批量图像修复管理器"""
    
    def __init__(self, worker: InpaintWorker):
        self.worker = worker
        self._progress = 0
        self._total = 0
    
    def submit_batch(self, 
                     tasks: List[dict],
                     progress_callback=None,
                     finished_callback=None):
        """
        提交批量任务
        tasks: [{'img': ..., 'mask': ..., 'rect': ...}, ...]
        """
        self._total = len(tasks)
        self._progress = 0
        
        for task_dict in tasks:
            self.worker.add_task(
                img=task_dict['img'],
                mask=task_dict['mask'],
                inpaint_rect=task_dict.get('rect'),
                priority=TaskPriority.LOW,
                callback=self._on_single_finished
            )
    
    def _on_single_finished(self, result):
        self._progress += 1
        progress_pct = int(self._progress / self._total * 100)
        # 触发进度更新
