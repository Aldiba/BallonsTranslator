from typing import Union, Tuple, Callable, List
import os.path as osp

import cv2
import numpy as np
from qtpy.QtGui import QColor, QPixmap, QImage

from .misc import pixmap2ndarray, ndarray2pixmap


def apply_edge_roughness(img: np.ndarray,
                         edge_strength: float = 0.5,
                         edge_hardness: float = 0.5,
                         ) -> np.ndarray:
    """Apply rough/jagged edge effect to a rendered text RGBA image (in-place).

    Uses sigmoid threshold on noise-displaced alpha, inspired by labi.py.
    Extruded pixels are filled with the dominant text foreground color so
    the rough edges match the text color.
    """
    h, w = img.shape[:2]
    alpha = img[..., 3].astype(np.float32) / 255.0
    alpha_u8 = (alpha * 255).astype(np.uint8)

    # Sample dominant text foreground color (for extruded edge pixels)
    text_body = img[(alpha_u8 > 180) & (alpha_u8 <= 255)]
    if len(text_body) > 0:
        fg_color = np.median(text_body[:, :3], axis=0).astype(np.uint8)
    else:
        fg_color = np.array([0, 0, 0], dtype=np.uint8)

    # Dilated mask: defines the zone where edge noise operates
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    dilated_u8 = cv2.dilate(alpha_u8, kernel, iterations=2)
    dilated = dilated_u8.astype(np.float32) / 255.0
    dilated_mask = dilated > 0.05

    # Multi-scale noise for organic roughness
    noise_fine = np.random.randn(h, w).astype(np.float32)
    ch, cw = max(1, h // 8), max(1, w // 8)
    noise_coarse = np.random.randn(ch, cw).astype(np.float32)
    noise_coarse = cv2.resize(noise_coarse, (w, h), interpolation=cv2.INTER_LINEAR)
    noise_coarse = cv2.GaussianBlur(noise_coarse, (7, 7), 2.0)
    combined_noise = noise_coarse * 0.7 + noise_fine * 0.3

    # Displace alpha by noise, restricted to dilated zone
    distorted = alpha + combined_noise * (edge_strength * 0.6) * dilated_mask.astype(np.float32)

    # Sigmoid threshold: hardness controls slope
    threshold = 0.5 - (edge_hardness * 0.2)
    slope = 10.0 + edge_hardness * 40.0
    new_alpha = 1.0 / (1.0 + np.exp(-slope * (distorted - threshold)))

    # Only within dilated zone; outside stays 0
    new_alpha = new_alpha * dilated_mask.astype(np.float32)

    # Identify extruded pixels: new alpha > old alpha (edge grew outward)
    extruded = (new_alpha > 0.01) & (alpha < 0.02)
    # Fill extruded pixels with text foreground color
    img[extruded, :3] = fg_color

    img[..., 3] = np.clip(new_alpha * 255, 0, 255).astype(np.uint8)
    return img


def generate_grain_overlay(h: int, w: int,
                           grain_strength: float = 0.5,
                           grain_size: float = 0.5,
                           seed: int = 0,
                           ) -> np.ndarray:
    """Generate a grain overlay with continuous alpha — no hard binary threshold.

    grain_strength: 0 = fully opaque (no grain visible), 1 = brightest
                    noise areas become fully transparent (binary cutout).
    grain_size: particle radius, 0 = ~0.5px specks, 1 = ~5px blobs.
                Scales the Gaussian blur sigma smoothly.
    seed: deterministic seed for reproducible noise.
    """
    rng = np.random.RandomState(seed)

    # Full-resolution Gaussian noise
    noise = rng.randn(h, w).astype(np.float32)

    # Smooth blur sigma — grain_size maps continuously
    blur_sigma = grain_size * 4.0 + 0.1   # 0 → 0.1 (tiny specks), 1 → 4.1 (big blobs)
    if blur_sigma > 0.3:
        ksize = max(3, int(blur_sigma * 2 + 0.5) | 1)
        noise = cv2.GaussianBlur(noise, (ksize, ksize), blur_sigma)

    # |noise| → normalize to 0..1 → continuous alpha
    noise_abs = np.abs(noise)
    nmin, nmax = noise_abs.min(), noise_abs.max()
    if nmax > nmin:
        noise_norm = (noise_abs - nmin) / (nmax - nmin)
    else:
        noise_norm = np.zeros_like(noise_abs)

    # grain_strength controls depth: 0 → alpha=1 everywhere, 1 → fully transparent at peaks
    alpha = 1.0 - noise_norm * grain_strength
    alpha = np.clip(alpha, 0.0, 1.0)

    overlay = np.zeros((h, w, 4), dtype=np.uint8)
    overlay[..., :3] = 255
    overlay[..., 3] = (alpha * 255).astype(np.uint8)
    return overlay


def apply_texture_effect(img: Union[QPixmap, QImage, np.ndarray],
                         edge_enabled: bool = False,
                         edge_strength: float = 0.5,
                         edge_hardness: float = 0.5,
                         grain_enabled: bool = False,
                         grain_strength: float = 0.5,
                         grain_size: float = 0.5,
                         grain_seed: int = 0,
                         ) -> Tuple[np.ndarray, np.ndarray | None]:
    """Apply edge roughness to image and/or generate a grain overlay.

    Returns:
        (modified_image, grain_overlay_or_None)
        grain_overlay is RGBA (H,W,4), white with binary alpha.
        Draw it over the final text with DestinationIn to punch grain holes.
    """
    if not isinstance(img, np.ndarray):
        img = pixmap2ndarray(img, keep_alpha=True)

    h, w = img.shape[:2]

    if edge_enabled and edge_strength > 0:
        img = apply_edge_roughness(img, edge_strength, edge_hardness)

    grain_overlay = None
    if grain_enabled and grain_strength > 0:
        grain_overlay = generate_grain_overlay(h, w, grain_strength, grain_size, seed=grain_seed)

    return img, grain_overlay


def apply_shadow_effect(img: Union[QPixmap, QImage, np.ndarray], color: QColor, strength=1.0, radius=21) -> Tuple[
    QPixmap, np.ndarray, np.ndarray]:
    if isinstance(color, QColor):
        color = [color.red(), color.green(), color.blue()]
    color = color[:3]  # only use RGB channels, discard any alpha

    if not isinstance(img, np.ndarray):
        img = pixmap2ndarray(img, keep_alpha=True)

    mask = img[..., -1].copy()
    ksize = radius * 2 + 1
    mask = cv2.GaussianBlur(mask, (ksize, ksize), ksize / 6)
    if strength != 1:
        mask = np.clip(mask.astype(np.float32) * strength, 0, 255).astype(np.uint8)
    bg_img = np.zeros((img.shape[0], img.shape[1], 4), dtype=np.uint8)
    bg_img[..., :3] = np.array(color, np.uint8)
    bg_img[..., 3] = mask

    result = ndarray2pixmap(bg_img)
    return result, img


# ---------------------------------------------------------------------------
# Screentone (网点) — 图案 tile × 文字形状遮罩
# ---------------------------------------------------------------------------

_screentone_cache: dict = {}


def load_screentone_alpha(pattern: str) -> np.ndarray:
    """Load a screentone pattern tile from data/screentones/ and return its
    alpha channel as np.ndarray (uint8). Cached. Returns None if not found."""
    global _screentone_cache
    if pattern in _screentone_cache:
        return _screentone_cache[pattern]
    from utils import shared as C
    path = osp.join(C.SCREENTONE_DIR, pattern)
    if not osp.exists(path):
        return None
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return None
    if img.ndim == 2:
        alpha = img
    elif img.shape[2] == 4:
        alpha = img[..., 3]
    else:
        alpha = img[..., 0]
    _screentone_cache[pattern] = alpha
    return alpha


def apply_screentone_effect(img: Union[QPixmap, np.ndarray],
                            pattern: str,
                            invert: bool = False,
                            scale: float = 0.5,
                            bg_color: List = None) -> np.ndarray:
    """
    网点效果：文字形状内每像素 = 纯文字色 或 纯背景色（无颜色混合 → 无羽化）。

    组成模型：
        - 文字形状区域内填满背景色 (bg_color) 作为底层
        - 图案遮罩的"点"处填充文字色（浮在背景色之上）
        - 图案用最近邻缩放 + 硬阈值 → 硬边，缩放不产生软边

    参数:
        img: 渲染好的文字 RGBA（QPixmap 或 numpy array）
        pattern: data/screentones/ 下的图案文件名
        invert: 反转图案 alpha（点处露背景色，其余文字色）
        scale: 图案缩放 0~1，映射到每格像素大小
        bg_color: 背景色 [R,G,B]，默认白
    返回: 网点化后的 numpy RGBA 图像
    """
    if not isinstance(img, np.ndarray):
        img = pixmap2ndarray(img, keep_alpha=True)

    alpha_tile = load_screentone_alpha(pattern)
    if alpha_tile is None:
        return img

    h, w = img.shape[:2]
    text_shape = img[..., 3] > 0
    if not text_shape.any():
        return img

    # 每格像素大小: scale 0→6px, 1→48px
    cell_px = max(2, int(round(6 + scale * 42)))
    ph, pw = alpha_tile.shape[:2]
    if ph == 0 or pw == 0:
        return img

    # 最近邻缩放 tile 到 cell_px 见方，再平铺覆盖 (h, w)
    if ph != cell_px or pw != cell_px:
        scaled = cv2.resize(alpha_tile, (cell_px, cell_px), interpolation=cv2.INTER_NEAREST)
    else:
        scaled = alpha_tile
    tiled = np.tile(scaled, (h // cell_px + 1, w // cell_px + 1))[:h, :w]

    # 硬阈值: 图案像素 > 127 → 文字色位置; 否则背景色位置
    filled = tiled > 127
    if invert:
        filled = ~filled

    if bg_color is None:
        bg = np.array([255, 255, 255], dtype=np.uint8)
    else:
        bg = np.array(bg_color[:3], dtype=np.uint8)

    result = img.copy()
    empty = (~filled) & text_shape
    result[empty, :3] = bg
    return result
