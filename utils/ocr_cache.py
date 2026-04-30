# utils/ocr_cache.py
"""OCR 结果缓存，避免重复识别"""

import hashlib
import numpy as np
from typing import Optional, Dict


class OCRResultCache:
    """OCR 结果缓存类"""
    
    _cache: Dict[str, dict] = {}
    _max_size: int = 1000  # 最大缓存数量
    
    @classmethod
    def get_cache_key(cls, img: np.ndarray, vertical: bool, roi: List[int] = None) -> str:
        """
        生成缓存键
        
        使用图像内容的 MD5 hash，确保相同图像返回相同键
        """
        # 缩放图像减少内存（可选）
        if img.size > 10000:
            # 取关键区域做 hash
            h, w = img.shape[:2]
            step = max(1, min(h, w) // 100)
            sample = img[::step, ::step]
        else:
            sample = img
        
        h = hashlib.md5(sample.tobytes()).hexdigest()[:16]
        v = 'v' if vertical else 'h'
        
        if roi:
            return f"{h}_{v}_{roi[0]}_{roi[1]}_{roi[2]}_{roi[3]}"
        return f"{h}_{v}"
    
    @classmethod
    def get(cls, img: np.ndarray, vertical: bool, roi: List[int] = None) -> Optional[dict]:
        """获取缓存结果"""
        key = cls.get_cache_key(img, vertical, roi)
        return cls._cache.get(key)
    
    @classmethod
    def set(cls, img: np.ndarray, vertical: bool, result: dict, roi: List[int] = None):
        """缓存结果"""
        # 缓存已满，清除最老的
        if len(cls._cache) >= cls._max_size:
            # 简单策略：清除一半
            keys = list(cls._cache.keys())[:cls._max_size // 2]
            for k in keys:
                del cls._cache[k]
        
        key = cls.get_cache_key(img, vertical, roi)
        cls._cache[key] = result
    
    @classmethod
    def clear(cls):
        """清空缓存"""
        cls._cache.clear()
    
    @classmethod
    def size(cls) -> int:
        return len(cls._cache)
