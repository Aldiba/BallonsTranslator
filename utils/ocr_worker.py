# ui/ocr_worker.py
from qtpy.QtCore import QObject, Signal, QThreadPool, QRunnable
from typing import Optional, List, Dict
import numpy as np

from utils.ocr_task_queue import OCRTask, OCRTaskQueue, OCRTaskPriority
from utils.logger import logger as LOGGER

class OCRTaskRunner(QRunnable):
    """OCR任务运行器（可并行）"""
    
    def __init__(self, task: OCRTask, ocr_module, callback):
        super().__init__()
        self.task = task
        self.ocr_module = ocr_module
        self.callback = callback
        self.setAutoDelete(True)
    
    def run(self):
        """执行OCR识别"""
        try:
            result = self.ocr_module.recognize(
                self.task.img,
                vertical=self.task.vertical
            )
            
            # 封装结果
            ocr_result = {
                'task_id': self.task.task_id,
                'text': result.get('text', ''),
                'conf': result.get('conf', 0),
                'roi': self.task.roi,
                'page_key': self.task.page_key
            }
            
            if self.callback:
                self.callback(ocr_result)
                
        except Exception as e:
            logger = LOGGER
            logger.error(f"OCR task {self.task.task_id} failed: {e}")
            if self.callback:
                self.callback(None, error=str(e))

class OCRWorker(QObject):
    """异步OCR工作器"""
    
    # 信号定义
    task_started = Signal(str)                 # task_id
    task_progress = Signal(str, int)           # task_id, progress
    task_finished = Signal(dict)               # ocr_result
    task_failed = Signal(str, str)             # task_id, error
    batch_progress = Signal(int, int)          # current, total
    
    def __init__(self, ocr_module, parent=None):
        super().__init__(parent)
        self._ocr_module = ocr_module
        self._task_queue = OCRTaskQueue(max_workers=2)
        self._threadpool = QThreadPool()
        self._threadpool.setMaxThreadCount(2)
        self._running_task_count = 0
        # 进度追踪
        self._total_submitted = 0
        self._total_finished = 0
    
    def add_task(self, 
                 img: np.ndarray,
                 roi: List[int],
                 page_key: str,
                 vertical: bool = False,
                 priority: int = OCRTaskPriority.NORMAL,
                 callback=None) -> str:
        """添加OCR任务"""
        import uuid
        task_id = str(uuid.uuid4())[:8]
        
        task = OCRTask(
            task_id=task_id,
            img=img,
            roi=roi,
            page_key=page_key,
            vertical=vertical,
            priority=priority,
            callback=callback
        )
        
        self._task_queue.add_task(task)
        LOGGER.info(f"[OCRWorker] Added task {task_id}, pending: {self._task_queue.pending_count}")
        
        # 启动处理
        self._process_next()
        
        return task_id
    
    def _process_next(self):
        """处理下一个任务"""
        task = self._task_queue.get_next_task()
        if task is None:
            return
        
        self._task_queue.mark_running(task)
        self._running_task_count += 1
        self.task_started.emit(task.task_id)
        
        # 创建运行器并提交到线程池
        runner = OCRTaskRunner(
            task=task,
            ocr_module=self._ocr_module,
            callback=self._on_task_finished
        )
        self._threadpool.start(runner)
    
    def _on_task_finished(self, result: dict = None, error: str = None):
        """任务完成回调"""
        self._running_task_count -= 1
        
        if result:
            self._task_queue.mark_finished(result['task_id'], result)
            self.task_finished.emit(result)
        else:
            self.task_failed.emit('', error or 'Unknown error')
        
        # 处理下一个任务
        self._process_next()
    
    def add_batch(self, tasks: List[dict], progress_callback=None):
        """批量添加任务"""
        self._total_submitted += len(tasks)
        
        for task_dict in tasks:
            # 检查缓存
            cached = OCRResultCache.get(
                task_dict['img'],
                task_dict.get('vertical', False),
                task_dict.get('roi')
            )
            
            if cached:
                # 使用缓存结果，跳过实际 OCR
                self._total_finished += 1
                result = {
                    'task_id': 'cached',
                    'text': cached['text'],
                    'conf': cached['conf'],
                    'roi': task_dict.get('roi', []),
                    'page_key': task_dict.get('page_key', '')
                }
                self.task_finished.emit(result)
                continue
            
            # 正常添加任务
            self.add_task(
                img=task_dict['img'],
                roi=task_dict['roi'],
                page_key=task_dict.get('page_key', ''),
                vertical=task_dict.get('vertical', False),
                priority=OCRTaskPriority.LOW,
                callback=progress_callback
            )
    
    def _on_task_finished(self, result: dict = None, error: str = None):
        """任务完成回调"""
        self._running_task_count -= 1
        self._total_finished += 1
        
        if result:
            # 缓存结果
            # 注意：需要记录原始图像用于缓存（可能需要调整）
            self._task_queue.mark_finished(result['task_id'], result)
            self.task_finished.emit(result)
            
            # 发送批量进度
            self.batch_progress.emit(self._total_finished, self._total_submitted)
        else:
            self.task_failed.emit('', error or 'Unknown error')
        
        # 继续处理下一个
        self._process_next()
    
    def cancel_all(self):
        """取消所有待处理任务"""
        self._task_queue.clear()
        LOGGER.info("[OCRWorker] All pending tasks cancelled")
    
    def get_pending_count(self) -> int:
        return self._task_queue.pending_count + self._running_task_count
