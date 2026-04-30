# utils/ocr_utils.py
"""OCR 辅助工具函数"""

import numpy as np
from typing import List, Tuple


def split_for_ocr(img: np.ndarray, max_size: int = 1024) -> List[Tuple[np.ndarray, List[int]]]:
    """
    分块处理大图像，避免显存溢出
    
    Args:
        img: 输入图像
        max_size: 单块最大尺寸
    
    Returns:
        [(图像块, [x1, y1, x2, y2]), ...]
    """
    h, w = img.shape[:2]
    
    # 小图像直接返回
    if h <= max_size and w <= max_size:
        return [(img, [0, 0, w, h])]
    
    # 分块
    blocks = []
    for y in range(0, h, max_size):
        for x in range(0, w, max_size):
            y2 = min(y + max_size, h)
            x2 = min(x + max_size, w)
            block = img[y:y2, x:x2]
            blocks.append((block, [x, y, x2, y2]))
    
    return blocks


def merge_ocr_results(results: List[dict], blocks_layout: List[List[int]]) -> dict:
    """
    合并分块 OCR 结果
    
    Args:
        results: 各块的 OCR 结果
        blocks_layout: 各块的坐标信息 [x1, y1, x2, y2]
    
    Returns:
        合并后的结果
    """
    if not results:
        return {'text': '', 'conf': 0}
    
    # 按位置排序并合并文本
    sorted_results = sorted(zip(blocks_layout, results), key=lambda x: (x[0][1], x[0][0]))
    
    texts = [r.get('text', '') for _, r in sorted_results]
    confs = [r.get('conf', 0) for _, r in sorted_results]
    
    return {
        'text': ''.join(texts),
        'conf': sum(confs) / len(confs) if confs else 0
    }
