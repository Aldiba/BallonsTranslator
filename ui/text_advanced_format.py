from typing import Any, Callable

from qtpy.QtWidgets import QSizePolicy, QVBoxLayout, QPushButton, QGroupBox, QLabel, QHBoxLayout, QSpinBox
from qtpy.QtCore import Signal, Qt
from qtpy.QtGui import QIcon

from .custom_widget import SmallColorPickerLabel, SmallParamLabel, PanelArea, SmallSizeControlLabel, SmallSizeComboBox, SmallParamLabel, SmallSizeComboBox, SmallComboBox, TextCheckerLabel, ParamSlider
from utils.fontformat import FontFormat
import random as _random


class TextShadowGroup(QGroupBox):
    def __init__(self, on_param_changed: Callable = None, title=None):
        super().__init__(title=title)
        self.on_param_changed = on_param_changed

        self.xoffset_box = SmallSizeComboBox([-2, 2], 'shadow_xoffset', self)
        self.xoffset_box.setToolTip(self.tr("Set X offset"))
        self.xoffset_box.param_changed.connect(self.on_offset_changed)
        self.xoffset_label = SmallSizeControlLabel(self, direction=1, text='X', alignment=Qt.AlignmentFlag.AlignCenter)
        self.xoffset_label.size_ctrl_changed.connect(self.xoffset_box.changeByDelta)
        self.xoffset_label.btn_released.connect(self.on_offset_changed)
        xoffset_layout = QHBoxLayout()
        xoffset_layout.addWidget(self.xoffset_label)
        xoffset_layout.addWidget(self.xoffset_box)

        self.yoffset_box = SmallSizeComboBox([-2, 2], 'shadow_yoffset', self)
        self.yoffset_box.setToolTip(self.tr("Set Y offset"))
        self.yoffset_box.param_changed.connect(self.on_offset_changed)
        self.yoffset_label = SmallSizeControlLabel(self, direction=1, text='Y', alignment=Qt.AlignmentFlag.AlignCenter)
        self.yoffset_label.size_ctrl_changed.connect(self.yoffset_box.changeByDelta)
        self.yoffset_label.btn_released.connect(self.on_offset_changed)
        yoffset_layout = QHBoxLayout()
        yoffset_layout.addWidget(self.yoffset_label)
        yoffset_layout.addWidget(self.yoffset_box)

        self.color_label = SmallColorPickerLabel(self, param_name='shadow_color')

        self.strength_box = SmallSizeComboBox([0, 3], 'shadow_strength', self)
        self.strength_box.setToolTip(self.tr("Set Shadow Strength"))
        self.strength_box.param_changed.connect(self.on_param_changed)
        self.strength_label = SmallSizeControlLabel(self, direction=1, text=self.tr('Strength'), alignment=Qt.AlignmentFlag.AlignCenter)
        self.strength_label.size_ctrl_changed.connect(lambda x : self.strength_box.changeByDelta(x, multiplier=0.03))
        self.strength_label.btn_released.connect(lambda : self.on_param_changed('shadow_strength', self.strength_box.value()))
        strength_layout = QHBoxLayout()
        strength_layout.addWidget(self.strength_label)
        strength_layout.addWidget(self.strength_box)

        self.radius_box = SmallSizeComboBox([0, 2], 'shadow_radius', self)
        self.radius_box.setToolTip(self.tr("Set Shadow Radius"))
        self.radius_box.param_changed.connect(self.on_param_changed)
        self.radius_label = SmallSizeControlLabel(self, direction=1, text=self.tr('Radius'), alignment=Qt.AlignmentFlag.AlignCenter)
        self.radius_label.size_ctrl_changed.connect(self.radius_box.changeByDelta)
        self.radius_label.btn_released.connect(lambda : self.on_param_changed('shadow_radius', self.radius_box.value()))
        radius_layout = QHBoxLayout()
        radius_layout.addWidget(self.radius_label)
        radius_layout.addWidget(self.radius_box)

        hlayout2 = QHBoxLayout()
        hlayout2.addWidget(self.color_label)
        hlayout2.addLayout(strength_layout)
        hlayout2.addLayout(radius_layout)

        yoffset_layout = QHBoxLayout()
        yoffset_layout.addWidget(self.yoffset_label)
        yoffset_layout.addWidget(self.yoffset_box)

        offset_label = SmallParamLabel(self.tr('Offset'))
        offset_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)
        offset_row = QHBoxLayout()
        offset_row.addWidget(offset_label)
        offset_row.addLayout(xoffset_layout)
        offset_row.addLayout(yoffset_layout)

        layout = QVBoxLayout(self)
        layout.addLayout(offset_row)
        layout.addLayout(hlayout2)

    def on_offset_changed(self, *args, **kwargs):
        self.on_param_changed('shadow_offset', [self.xoffset_box.value(), self.yoffset_box.value()])


class TextGradientGroup(QGroupBox):
    def __init__(self, on_param_changed: Callable = None):
        super().__init__()
        self.setTitle(self.tr('Gradient'))
        self.on_param_changed = on_param_changed

        self.start_picker = SmallColorPickerLabel(self, param_name='gradient_start_color')
        start_picker_label = SmallParamLabel(self.tr('Start Color'), alignment=Qt.AlignmentFlag.AlignCenter)
        start_picker_layout = QHBoxLayout()
        start_picker_layout.addWidget(start_picker_label)
        start_picker_layout.addWidget(self.start_picker)

        self.end_picker = SmallColorPickerLabel(self, param_name='gradient_end_color')
        end_picker_label = SmallParamLabel(self.tr('End Color'), alignment=Qt.AlignmentFlag.AlignCenter)
        end_picker_layout = QHBoxLayout()
        end_picker_layout.addWidget(end_picker_label)
        end_picker_layout.addWidget(self.end_picker)

        self.enable_checker = TextCheckerLabel(self.tr('Enable'))
        self.enable_checker.checkStateChanged.connect(lambda checked: self.on_param_changed('gradient_enabled', checked))

        self.angle_box = SmallSizeComboBox([0, 359], 'gradient_angle', self)
        self.angle_box.setToolTip(self.tr("Set Gradient Angle"))
        self.angle_box.param_changed.connect(self.on_param_changed)
        self.angle_label = SmallSizeControlLabel(self, direction=1, text=self.tr('Angle'), alignment=Qt.AlignmentFlag.AlignCenter)
        self.angle_label.size_ctrl_changed.connect(lambda x : self.angle_box.changeByDelta(x, multiplier=1))
        self.angle_label.btn_released.connect(lambda : self.on_param_changed('gradient_angle', self.angle_box.value()))
        angle_layout = QHBoxLayout()
        angle_layout.addWidget(self.angle_label)
        angle_layout.addWidget(self.angle_box)

        self.size_box = SmallSizeComboBox([0.5, 2], 'gradient_size', self)
        self.size_box.setToolTip(self.tr("Set Gradient Size"))
        self.size_box.param_changed.connect(self.on_param_changed)
        self.size_label = SmallSizeControlLabel(self, direction=1, text=self.tr('Size'), alignment=Qt.AlignmentFlag.AlignCenter)
        self.size_label.size_ctrl_changed.connect(lambda x : self.size_box.changeByDelta(x, multiplier=0.02))
        self.size_label.btn_released.connect(lambda : self.on_param_changed('gradient_size', self.size_box.value()))
        size_layout = QHBoxLayout()
        size_layout.addWidget(self.size_label)
        size_layout.addWidget(self.size_box)

        hlayout1 = QHBoxLayout()
        hlayout1.addLayout(start_picker_layout)
        hlayout1.addLayout(end_picker_layout)
        hlayout1.addWidget(self.enable_checker)
        # hlayout1.addStretch(-1)

        hlayout2 = QHBoxLayout()
        hlayout2.addLayout(angle_layout)
        hlayout2.addLayout(size_layout)

        layout = QVBoxLayout(self)
        layout.addLayout(hlayout1)
        layout.addLayout(hlayout2)


class TextTextureGroup(QGroupBox):
    """Texture effect controls — master toggle + 4 vertical slider rows."""

    def __init__(self, on_param_changed: Callable = None):
        super().__init__()
        self.setTitle(self.tr('Texture'))
        self.on_param_changed = on_param_changed

        # ── Master toggle ───────────────────────────────────────────────
        self.master_checker = TextCheckerLabel(self.tr('Enable'))
        self.master_checker.checkStateChanged.connect(
            lambda checked: self.on_param_changed('texture_enabled', checked)
        )

        # ── Edge roughness ──────────────────────────────────────────────
        self.edge_checker = TextCheckerLabel(self.tr('Rough Edge'))
        self.edge_checker.checkStateChanged.connect(
            lambda checked: self.on_param_changed('texture_edge_enabled', checked)
        )

        self.edge_strength_slider = ParamSlider(
            'texture_edge_strength', min_val=0, max_val=100, step=1, value=50,
        )
        self.edge_strength_slider.paramwidget_edited.connect(self._on_float_param)
        edge_strength_label = SmallParamLabel(
            self.tr('Edge Strength'), alignment=Qt.AlignmentFlag.AlignLeft,
        )
        edge_str_row = QHBoxLayout()
        edge_str_row.addWidget(edge_strength_label)
        edge_str_row.addWidget(self.edge_strength_slider)
        edge_str_row.addStretch(-1)

        self.edge_hardness_slider = ParamSlider(
            'texture_edge_hardness', min_val=0, max_val=100, step=1, value=50,
        )
        self.edge_hardness_slider.paramwidget_edited.connect(self._on_float_param)
        edge_hard_label = SmallParamLabel(
            self.tr('Edge Hardness'), alignment=Qt.AlignmentFlag.AlignLeft,
        )
        edge_hard_row = QHBoxLayout()
        edge_hard_row.addWidget(edge_hard_label)
        edge_hard_row.addWidget(self.edge_hardness_slider)
        edge_hard_row.addStretch(-1)

        # ── Internal grain ──────────────────────────────────────────────
        self.grain_checker = TextCheckerLabel(self.tr('Grain'))
        self.grain_checker.checkStateChanged.connect(
            lambda checked: self.on_param_changed('texture_grain_enabled', checked)
        )

        self.grain_strength_slider = ParamSlider(
            'texture_grain_strength', min_val=0, max_val=100, step=1, value=50,
        )
        self.grain_strength_slider.paramwidget_edited.connect(self._on_float_param)
        grain_str_label = SmallParamLabel(
            self.tr('Grain Strength'), alignment=Qt.AlignmentFlag.AlignLeft,
        )
        grain_str_row = QHBoxLayout()
        grain_str_row.addWidget(grain_str_label)
        grain_str_row.addWidget(self.grain_strength_slider)
        grain_str_row.addStretch(-1)

        self.grain_size_slider = ParamSlider(
            'texture_grain_size', min_val=0, max_val=100, step=1, value=50,
        )
        self.grain_size_slider.paramwidget_edited.connect(self._on_float_param)
        grain_size_label = SmallParamLabel(
            self.tr('Grain Size'), alignment=Qt.AlignmentFlag.AlignLeft,
        )
        grain_size_row = QHBoxLayout()
        grain_size_row.addWidget(grain_size_label)
        grain_size_row.addWidget(self.grain_size_slider)
        grain_size_row.addStretch(-1)

        # ── Seed ─────────────────────────────────────────────────────────
        self.seed_spin = QSpinBox()
        self.seed_spin.setRange(0, 999999)
        self.seed_spin.setValue(0)
        self.seed_spin.setToolTip(self.tr('Noise seed, 0 = random each time'))
        self.seed_spin.setMinimumWidth(72)
        self.seed_spin.valueChanged.connect(self._on_seed_changed)

        self.seed_random_btn = QPushButton('🎲')
        self.seed_random_btn.setFixedSize(24, 24)
        self.seed_random_btn.setToolTip(self.tr('Random seed'))
        self.seed_random_btn.clicked.connect(self._on_random_seed)

        seed_label = SmallParamLabel(
            self.tr('Seed'), alignment=Qt.AlignmentFlag.AlignLeft,
        )
        seed_row = QHBoxLayout()
        seed_row.addWidget(seed_label)
        seed_row.addWidget(self.seed_spin)
        seed_row.addWidget(self.seed_random_btn)
        seed_row.addStretch(-1)

        # ── Vertical layout ─────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.addWidget(self.master_checker)
        layout.addWidget(self.edge_checker)
        layout.addLayout(edge_str_row)
        layout.addLayout(edge_hard_row)
        layout.addWidget(self.grain_checker)
        layout.addLayout(grain_str_row)
        layout.addLayout(grain_size_row)
        layout.addLayout(seed_row)

    def _on_float_param(self, param_key: str, value_str: str):
        self.on_param_changed(param_key, int(value_str) / 100.0)

    def _on_seed_changed(self, value: int):
        self.on_param_changed('texture_seed', value)

    def _on_random_seed(self):
        self.seed_spin.setValue(_random.randint(1, 999999))


class TextAdvancedFormatPanel(PanelArea):

    param_changed = Signal(str, object)

    def __init__(self, panel_name: str, config_name: str, config_expand_name: str, on_format_changed: Callable):
        super().__init__(panel_name, config_name, config_expand_name)

        self.active_format: FontFormat = None
        self.on_format_changed = on_format_changed

        self.linespacing_type_combobox = SmallComboBox(
            parent=self,
            options=[
                self.tr("Proportional"),
                self.tr("Distance")
            ]
        )
        self.linespacing_type_combobox.activated.connect(self.on_linespacing_type_changed)
        linespacing_type_label = SmallParamLabel(self.tr('Line Spacing Type'))
        linespacing_type_layout = QHBoxLayout()
        linespacing_type_layout.addWidget(linespacing_type_label)
        linespacing_type_layout.addWidget(self.linespacing_type_combobox)

        self.opacity_box = SmallSizeComboBox([0, 1], 'opacity', self, init_value=1.)
        self.opacity_box.setToolTip(self.tr("Set Text Opacity"))
        self.opacity_box.param_changed.connect(self.on_format_changed)
        self.opacity_label = SmallSizeControlLabel(self, direction=1, text=self.tr('Opacity'), alignment=Qt.AlignmentFlag.AlignCenter)
        self.opacity_label.size_ctrl_changed.connect(self.opacity_box.changeByDelta)
        self.opacity_label.btn_released.connect(lambda : self.on_format_changed('opacity', self.opacity_box.value()))
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(self.opacity_label)
        opacity_layout.addWidget(self.opacity_box)

        # self.tate_chu_yoko_checker = QFontChecker()
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.scrollContent.after_resized.connect(self.adjuset_size)

        self.shadow_group = TextShadowGroup(self.on_format_changed, title=self.tr('Shadow'))
        self.shadow_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.gradient_group = TextGradientGroup(self.on_format_changed)
        self.gradient_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        self.texture_group = TextTextureGroup(self.on_format_changed)
        self.texture_group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)

        hlayout = QHBoxLayout()
        hlayout.addLayout(linespacing_type_layout)
        hlayout.addLayout(opacity_layout)
        vlayout = QVBoxLayout()
        vlayout.addLayout(hlayout)
        vlayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        vlayout.addWidget(self.shadow_group)
        vlayout.addWidget(self.gradient_group)
        vlayout.addWidget(self.texture_group)

        self.setContentLayout(vlayout)
        self.vlayout = vlayout

    def adjuset_size(self):
        TEXT_ADVANCED_PANEL_MAXH = 300
        self.setFixedHeight(min(TEXT_ADVANCED_PANEL_MAXH, self.scrollContent.height()))

    def on_linespacing_type_changed(self):
        self.on_format_changed('line_spacing_type', self.linespacing_type_combobox.currentIndex())

    def set_active_format(self, font_format: FontFormat):
        self.active_format = font_format
        self.linespacing_type_combobox.setCurrentIndex(font_format.line_spacing_type)

        self.shadow_group.color_label.setPickerColor(font_format.shadow_color)
        self.shadow_group.strength_box.setValue(font_format.shadow_strength)
        self.shadow_group.radius_box.setValue(font_format.shadow_radius)
        self.shadow_group.xoffset_box.setValue(font_format.shadow_offset[0])
        self.shadow_group.yoffset_box.setValue(font_format.shadow_offset[1])

        self.gradient_group.size_box.setValue(font_format.gradient_size)
        self.gradient_group.angle_box.setValue(font_format.gradient_angle)
        self.gradient_group.enable_checker.setCheckState(font_format.gradient_enabled)
        self.gradient_group.start_picker.setPickerColor(font_format.gradient_start_color)
        self.gradient_group.end_picker.setPickerColor(font_format.gradient_end_color)
        # self.tate_chu_yoko_checker.setChecked(font_format.font)

        self.texture_group.master_checker.setCheckState(font_format.texture_enabled)
        self.texture_group.edge_checker.setCheckState(font_format.texture_edge_enabled)
        self.texture_group.edge_strength_slider.setValue(int(font_format.texture_edge_strength * 100))
        self.texture_group.edge_hardness_slider.setValue(int(font_format.texture_edge_hardness * 100))
        self.texture_group.grain_checker.setCheckState(font_format.texture_grain_enabled)
        self.texture_group.grain_strength_slider.setValue(int(font_format.texture_grain_strength * 100))
        self.texture_group.grain_size_slider.setValue(int(font_format.texture_grain_size * 100))
        self.texture_group.seed_spin.setValue(font_format.texture_seed)