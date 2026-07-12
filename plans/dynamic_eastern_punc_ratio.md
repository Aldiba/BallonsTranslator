# 竖排东方标点高度动态计算方案

## 现状分析

当前代码 [`ui/scene_textlayout.py:960`](ui/scene_textlayout.py:960) 中对于 `PUNSET_EASTERN_VERTICAL`（`、。，`）在竖排模式下的高度使用硬编码 `3/5`：

```python
if char in PUNSET_EASTERN_VERTICAL:
    tbr_h = cfmt.punc_actual_rect(line, char, cache=True, space_shift=space_shift)[3]*3/5
```

这意味着无论使用什么字体（明体、黑体、手写体），这些标点都被强制压缩到 `ink_h × 0.6`。不同字体中这些标点的物理尺寸比例是不同的。

## 改动方案

### 核心思路

新增一个基于字体度量的缓存函数，计算标点物理高度与参考汉字高度之比，再映射到视觉舒适的比例区间。

### 改动 1：新增函数 `get_eastern_punc_ratio()`

放在 [`ui/scene_textlayout.py`](ui/scene_textlayout.py) 顶部工具函数区（约 L85 附近，`_get_tight_rect_values` 之后）：

```python
@lru_cache(maxsize=512)
def get_eastern_punc_ratio(ffamily: str, size: float, weight: int, italic: bool) -> float:
    """
    根据字体度量动态计算竖排东方标点(、。，)的占用高度比例。
    用标点本身的 tightBoundingRect 高度与参考汉字(木)的 tightBoundingRect 高度
    之比来反映该字体中标点的真实物理比例，再映射到视觉舒适的区间。
    """
    fm = _font_metrics(ffamily, size, weight, italic)
    
    # 测量三种东方竖排标点的平均 tight rect 高度
    heights = []
    for c in '、。，':
        heights.append(fm.tightBoundingRect(c).height())
    avg_h = sum(heights) / len(heights)
    
    # 测量参考汉字的高度
    ref_h = fm.tightBoundingRect('木').height()
    if ref_h <= 0:
        return 0.6  # fallback
    
    # 物理比例：标点高度 / 汉字高度
    raw_ratio = avg_h / ref_h
    
    # 线性映射到视觉舒适区间 [0.4, 0.75]
    # 物理比例 = 0.3 → visual ≈ 0.47（标点很小的字体，如明体）
    # 物理比例 = 0.5 → visual ≈ 0.59（典型字体）
    # 物理比例 = 0.7 → visual ≈ 0.71（标点较大的字体，如黑体）
    visual_ratio = 0.35 + 0.6 * raw_ratio
    visual_ratio = min(0.75, max(0.4, visual_ratio))
    
    return visual_ratio
```

### 改动 2：修改 `layoutBlock` 中的硬编码 `3/5`

[`ui/scene_textlayout.py:960-961`](ui/scene_textlayout.py:960)：

**修改前：**
```python
if char in PUNSET_EASTERN_VERTICAL:
    tbr_h = cfmt.punc_actual_rect(line, char, cache=True, space_shift=space_shift)[3]*3/5
```

**修改后：**
```python
if char in PUNSET_EASTERN_VERTICAL:
    punc_ratio = get_eastern_punc_ratio(cfmt.family, cfmt.size, cfmt.weight, cfmt.font.italic())
    tbr_h = cfmt.punc_actual_rect(line, char, cache=True, space_shift=space_shift)[3] * punc_ratio
```

### 改动 3：核对 `updateDrawOffsets` 中的偏移逻辑

[`ui/scene_textlayout.py:648-650`](ui/scene_textlayout.py:648) 中的绘制偏移不需要修改，因为：
- `yoff = -act_rect[1]` 将标点顶部对齐到行顶
- `xoff = (line_width - act_rect[2] - act_rect[0])` 水平居中/右对齐

这些是绘制坐标偏移，与 `tbr_h`（空间分配）解耦，改高度比例不影响绘制定位。

### 影响范围

| 文件 | 位置 | 改动 |
|------|------|------|
| `ui/scene_textlayout.py` | ~L87 新增函数 | +15 行（含注释） |
| `ui/scene_textlayout.py` | L960-961 | 修改 2 行 |
| 其他文件 | — | 无影响 |

### 预期效果

- **明体/宋体**：标点物理比例小（~0.35） → 映射到 ~0.47，保持明体标点纤细的特点
- **黑体**：标点物理比例大（~0.55） → 映射到 ~0.63，自动适应较饱满的标点
- **手写体/艺术字体**：根据字体实际度量自适应，不再硬性压缩到 60%

### 潜在风险

1. **回归**：对于标点物理比例 ≈ 0.42 的典型字体，映射后 ≈ 0.60，与原来的 3/5 几乎一致，不会有视觉突变
2. **边缘字体**：极端的艺术字体可能映射到区间边界（0.4 或 0.75），有边界保护不会溢出
