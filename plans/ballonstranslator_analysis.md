# BallonsTranslator 项目架构分析报告

## 一、项目概述

BallonsTranslator 是一个基于深度学习的**漫画/图像翻译工具**，支持文本检测、OCR识别、机器翻译和图像编辑等功能。项目采用 Python + Qt 构建，具有良好的模块化设计。

**核心技术栈：**
- **GUI框架：** Qt (PyQt5/PyQt6/PySide2/PySide6)
- **深度学习：** PyTorch (支持 CUDA/XPU/MPS/DirectML)
- **模块化设计：** Registry 模式 + Hooks 机制

## 二、系统架构

```
┌─────────────────────────────────────────────────────────┐
│                     UI Layer (Qt)                       │
│  MainWindow │ Canvas │ ConfigPanel │ TextPanel │ etc.   │
├─────────────────────────────────────────────────────────┤
│              Business Logic Layer                        │
│  ProjImgTrans │ SceneTextManager │ ModuleManager         │
├─────────────────────────────────────────────────────────┤
│                    Module Layer                           │
│  TextDetector │ OCR │ Translator │ Inpainter            │
├─────────────────────────────────────────────────────────┤
│                   Utils Layer                            │
│  TextBlock │ Registry │ Config │ Logger │ FontFormat    │
└─────────────────────────────────────────────────────────┘
```

### 2.1 模块层架构

项目采用 **Registry 模式** 管理各类模块：

- **[`modules/base.py`](modules/base.py)**：定义 `BaseModule` 基类，提供标准化的参数管理、设备选择、模型加载/卸载机制
- **[`modules/ocr/`](modules/ocr/)**：OCR 识别模块（mit 系列、manga_ocr、PaddleOCR、TuanziOCR 等）
- **[`modules/textdetector/`](modules/textdetector/)**：文本检测模块（CTD、YOLO、Tuanzi 等）
- **[`modules/translators/`](modules/translators/)**：翻译模块（Google、DeepL、ChatGPT、Sugoi 等 20+ 种翻译器）
- **[`modules/inpaint/`](modules/inpaint/)**：图像修复模块（AOT、Lama、PatchMatch）

**关键设计：**
- **参数标准化：** `standardize_module_params()` + `patch_module_params()` 实现配置合并
- **设备抽象：** 支持 CPU/CUDA/XPU/MPS/DirectML 自动选择
- **Hooks 机制：** 支持 `preprocess_hooks` 和 `postprocess_hooks` 扩展
- **懒加载：** 模型按需加载，减少启动时间和内存占用

### 2.2 数据结构

**`TextBlock`** 是核心数据结构，包含：
- 位置信息：`xyxy`, `lines`
- 文本内容：`text`, `translation`, `rich_text`
- 格式信息：`fontformat` (FontFormat 对象)
- 状态标志：`merged`, `src_is_vertical`

### 2.3 UI 层架构

采用 **FramelessWindow** 实现无边框窗口，自定义标题栏和窗口控制。

主要组件：
- **`MainWindow`**：主窗口，管理项目和工作流
- **`Canvas`**：图像显示和交互画布
- **`SceneTextManager`**：场景文本管理，包含 `TextPanel` 和 `SelectTextMiniMenu`
- **`ConfigPanel`**：配置面板

## 三、字体样式、预设与文本框界面定位

### 3.1 界面层次结构

```
MainWindow
  └── TextPanel (ui/scenetext_manager.py:302)
        ├── FontFormatPanel (ui/text_panel.py:246)
        │     ├── TextStylePresetPanel (ui/text_style_presets.py:262)
        │     └── TextAdvancedFormatPanel (ui/text_advanced_format.py)
        └── TextEditListScrollArea
```

### 3.2 关键组件位置

| 功能 | 文件路径 | 类/组件 |
|------|----------|---------|
| **字体样式数据** | [`utils/fontformat.py`](utils/fontformat.py:59) | `FontFormat` |
| **样式预设UI** | [`ui/text_style_presets.py`](ui/text_style_presets.py:262) | `TextStylePresetPanel` |
| **高级格式UI** | [`ui/text_advanced_format.py`](ui/text_advanced_format.py:1) | `TextAdvancedFormatPanel` |
| **字体格式面板** | [`ui/text_panel.py`](ui/text_panel.py:246) | `FontFormatPanel` |
| **文本编辑列表** | [`ui/scenetext_manager.py`](ui/scenetext_manager.py:302) | `TextPanel` |
| **主窗口** | [`ui/mainwindow.py`](ui/mainwindow.py:61) | `MainWindow` |

### 3.3 FontFormat 数据结构

[`utils/fontformat.py`](utils/fontformat.py:59) 中的 `FontFormat` 类包含以下属性：

```python
font_family: str       # 字体家族
font_size: float      # 字体大小
stroke_width: float   # 描边宽度
frgb: List # 前景色 RGB
srgb: List          # 阴影色 RGB
bold: bool          # 粗体
underline: bool     # 下划线
italic: bool        # 斜体
alignment: int      # 对齐方式 (0左对齐/1居中/2右对齐)
vertical: bool      # 竖排文本
font_weight: int    # 字重
line_spacing: float # 行间距
letter_spacing: float # 字间距
opacity: float      # 不透明度
shadow_radius: float  # 阴影半径
shadow_strength: float # 阴影强度
shadow_color: List # 阴影颜色
shadow_offset: List   # 阴影偏移
gradient_enabled: bool # 渐变启用
# ... 渐变相关属性
```

### 3.4 样式预设管理

[`ui/text_style_presets.py`](ui/text_style_presets.py:262) 中的 `TextStylePresetPanel`：
- 管理预设样式列表
- 支持新建、删除、导入导出样式
- 每个预设由 `TextStyleLabel` 表示
- 样式数据保存到 `config/stylesheet.css`

## 四、架构亮点

1. **插件式模块系统：** 新增翻译器或 OCR 只需继承 `BaseModule` 并使用 `@register_translator` 装饰器即可
2. **多后端支持：** 统一抽象 PyTorch 设备，支持 CUDA/XPU/MPS/DirectML
3. **配置热更新：** 模块参数自动合并和类型转换
4. **完善的中文本地化：** 内置 `translate/i18n/` 翻译文件

## 五、潜在改进点

1. **模块间耦合：** 部分模块直接依赖具体实现，抽象层可以更清晰
2. **错误处理：** 部分模块的错误处理可以更一致
3. **文档：** 缺少 API 文档和架构设计文档

## 六、技术债务

1. **废弃兼容代码：** `deprecated_attributes` 等废弃字段需要清理
2. **Windows 7 支持：** 需要安装 Python 3.8 单独运行，增加了维护负担
3. **macOS 应用打包：** 仍处于实验阶段