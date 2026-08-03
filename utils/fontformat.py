from typing import Union
import enum
import re
import copy

import numpy as np

from . import shared
from .structures import Tuple, Union, List, Dict, Config, field, nested_dataclass


def pt2px(pt, to_int=False) -> float:
    if to_int:
        return int(round(pt * shared.LDPI / 72.))
    else:
        return pt * shared.LDPI / 72.

def px2pt(px) -> float:
    return px / shared.LDPI * 72.


class LineSpacingType(enum.IntEnum):
    Proportional = 0
    Distance = 1


class TextAlignment(enum.IntEnum):
    Left = 0
    Center = 1
    Right = 2


fontweight_qt5_to_qt6 = {0: 100, 12: 200, 25: 300, 50: 400, 57: 500, 63: 600, 75: 700, 81: 800, 87: 900}
fontweight_qt6_to_qt5 = {100: 0, 200: 12, 300: 25, 400: 50, 500: 57, 600: 63, 700: 75, 800: 81, 900: 87}

fontweight_pattern = re.compile(r'font-weight:(\d+)', re.DOTALL)

def fix_fontweight_qt(weight: Union[str, int]):

    def _fix_html_fntweight(matched):
        weight = int(matched.group(1))
        return f'font-weight:{fix_fontweight_qt(weight)}'

    if weight is None:
        return None
    if isinstance(weight, int):
        if shared.FLAG_QT6 and weight < 100:
            if weight in fontweight_qt5_to_qt6:
                weight = fontweight_qt5_to_qt6[weight]
        if not shared.FLAG_QT6 and weight >= 100:
            if weight in fontweight_qt6_to_qt5:
                weight = fontweight_qt6_to_qt5[weight]
    if isinstance(weight, str):
        weight = fontweight_pattern.sub(lambda matched: _fix_html_fntweight(matched), weight)
    return weight


@nested_dataclass
class FontFormat(Config):

    font_family: str = shared.DEFAULT_FONT_FAMILY # to always apply shared.DEFAULT_FONT_FAMILY
    font_size: float = 24
    stroke_width: float = 0.
    frgb: List = field(default_factory=lambda: [0, 0, 0])
    srgb: List = field(default_factory=lambda: [0, 0, 0])
    bold: bool = False
    underline: bool = False
    italic: bool = False
    alignment: int = 0
    vertical: bool = False
    font_weight: int = None
    line_spacing: float = 1.2
    letter_spacing: float = 1.15
    opacity: float = 1.
    shadow_radius: float = 0.
    shadow_strength: float = 1.
    shadow_color: List = field(default_factory=lambda: [0, 0, 0])
    shadow_offset: List = field(default_factory=lambda: [0., 0.])
    gradient_enabled: bool = False
    gradient_start_color: List = field(default_factory=lambda: [0, 0, 0])
    gradient_end_color: List = field(default_factory=lambda: [255, 255, 255])
    gradient_angle: float = 0.
    gradient_size: float = 1.0
    _style_name: str = ''
    line_spacing_type: int = LineSpacingType.Proportional
    vertical_rtl_mode: int = 0  # 0=正常(全部旋转), 1=数字正过来, 2=字母正过来, 3=全部正过来
    strokes: List = field(default_factory=list)  # 多重描边: [{"width": float, "color": [R,G,B,A]}, ...] 从外到内
    path_type: int = 0  # 0=无路径形变, 1=弧形上弯(smile), 2=弧形下弯(frown), 3=贝塞尔
    path_data: List = field(default_factory=list)  # 路径参数: 弧形=[curvature(0~1)], 贝塞尔=[cp1x,cp1y,cp2x,cp2y,endx,endy]
    texture_enabled: bool = False  # 纹理总开关
    texture_edge_enabled: bool = False  # 边缘毛糙开关
    texture_edge_strength: float = 0.5  # 边缘毛糙强度 0.0 ~ 1.0
    texture_edge_hardness: float = 0.5  # 边缘硬度 0.0(柔和) ~ 1.0(硬像素锯齿)
    texture_grain_enabled: bool = False  # 内部噪点开关
    texture_grain_strength: float = 0.5  # 内部噪点强度 0.0 ~ 1.0
    texture_grain_size: float = 0.5  # 噪点粒度 0.0(细) ~ 1.0(粗)
    texture_seed: int = 0  # 噪声种子, 0=自动随机

    deprecated_attributes: dict = field(default_factory = lambda: dict())

    @property
    def size_pt(self):
        return px2pt(self.font_size)

    def __post_init__(self):
        da = self.deprecated_attributes
        if len(da) > 0:
            if 'size' in da:
                self.font_size = pt2px(da['size'])
            if 'weight' in da:
                self.font_weight = da['weight']
            if 'family' in da:
                self.font_family = da['family']

        self.font_weight = fix_fontweight_qt(self.font_weight)
        self.deprecated_attributes = {}

    def deepcopy(self):
        fmt_copyed: FontFormat = None
        fmt_copyed = copy.deepcopy(self)
        return fmt_copyed

    def merge(self, target: Config, compare: bool = False):
        if id(self) == id(target):
            return set()
        tgt_keys = target.annotations_set()
        updated_keys = set()
        for key in tgt_keys:
            if not hasattr(self, key):
                continue
            if compare:
                if key != '_style_name':
                    if isinstance(target[key], np.ndarray):
                        is_diff = np.any(self[key] != target[key])
                    else:
                        is_diff = self[key] != target[key]
                    if is_diff:
                        self.update(key, copy.deepcopy(target[key]))
                        updated_keys.add(key)
            else:
                self.update(key, copy.deepcopy(target[key]))
        return updated_keys

    def foreground_color(self):
        return [int(round(x)) for x in self.frgb]

    def stroke_color(self):
        return [int(round(x)) for x in self.srgb]

    @property
    def effective_strokes(self) -> list:
        """返回有效描边列表。向后兼容: strokes 为空时从 stroke_width + srgb 构造。"""
        if self.strokes:
            return [s for s in self.strokes if s.get("enabled", True)]
        if self.stroke_width > 0:
            return [{"width": self.stroke_width, "color": self.stroke_color()}]
        return []

    @property
    def has_stroke(self) -> bool:
        """是否有任何有效描边"""
        if self.strokes:
            return any(s.get("enabled", True) and s.get("width", 0) > 0 for s in self.strokes)
        return self.stroke_width > 0

    @property
    def has_texture(self) -> bool:
        """是否有纹理效果"""
        if not self.texture_enabled:
            return False
        return (self.texture_edge_enabled and self.texture_edge_strength > 0) \
            or (self.texture_grain_enabled and self.texture_grain_strength > 0)