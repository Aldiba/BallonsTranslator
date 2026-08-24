"""
网格像素画布手绘编辑器 — 创建可无缝平铺的网点图案。

图案数据模型: 一张 NxN 的 uint8 数组, 255=填充, 0=空白 (只存 alpha, 无颜色)。
保存为灰度 PNG 到 data/screentones/, 供 apply_screentone_effect 作为遮罩使用。
"""

import os
import os.path as osp

import cv2
import numpy as np

from qtpy.QtCore import Qt, QRectF, QPoint, QPointF, Signal
from qtpy.QtGui import QPainter, QColor, QPen, QBrush
from qtpy.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QWidget, QGroupBox,
)

from utils import shared as C

GRID_SIZES = [16, 32, 64, 128]


class PatternGridCanvas(QWidget):
    """网格像素画布：鼠标点击/拖拽填格或擦除。"""

    pattern_changed = Signal()

    def __init__(self, grid_size: int = 64, parent=None):
        super().__init__(parent)
        self.grid_size = grid_size
        self.paint_mode = True  # True=填, False=擦
        self.data = np.zeros((grid_size, grid_size), dtype=np.uint8)
        self.setMinimumSize(320, 320)
        self.setMouseTracking(True)
        self._last_cell = None

    def set_grid_size(self, size: int):
        self.grid_size = size
        self.data = np.zeros((size, size), dtype=np.uint8)
        self.update()
        self.pattern_changed.emit()

    def set_paint_mode(self, paint: bool):
        self.paint_mode = paint

    def clear(self):
        self.data[:] = 0
        self.update()
        self.pattern_changed.emit()

    def _cell_size(self) -> float:
        w = self.width() - 1
        h = self.height() - 1
        return min(w / self.grid_size, h / self.grid_size)

    def _pos_to_cell(self, pos: QPointF):
        cs = self._cell_size()
        col = int(pos.x() / cs)
        row = int(pos.y() / cs)
        if 0 <= row < self.grid_size and 0 <= col < self.grid_size:
            return row, col
        return None

    def mousePressEvent(self, e):
        cell = self._pos_to_cell(e.position())
        if cell is None:
            return
        self._last_cell = cell
        self._apply(cell)
        self.update()
        self.pattern_changed.emit()

    def mouseMoveEvent(self, e):
        if not e.buttons() & Qt.MouseButton.LeftButton:
            return
        cell = self._pos_to_cell(e.position())
        if cell is None or cell == self._last_cell:
            return
        self._last_cell = cell
        self._apply(cell)
        self.update()
        self.pattern_changed.emit()

    def mouseReleaseEvent(self, e):
        self._last_cell = None

    def _apply(self, cell):
        r, c = cell
        self.data[r, c] = 255 if self.paint_mode else 0

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)

        # 背景
        painter.fillRect(self.rect(), QColor(245, 245, 245))

        cs = self._cell_size()
        fill_color = QColor(40, 40, 40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(fill_color))
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                if self.data[r, c] > 0:
                    painter.drawRect(QRectF(c * cs, r * cs, cs, cs))

        # 网格线
        painter.setPen(QPen(QColor(200, 200, 200), 1))
        for i in range(self.grid_size + 1):
            x = i * cs
            painter.drawLine(QPoint(int(x), 0), QPoint(int(x), self.height()))
        for j in range(self.grid_size + 1):
            y = j * cs
            painter.drawLine(QPoint(0, int(y)), QPoint(self.width(), int(y)))


class PatternPreviewWidget(QWidget):
    """平铺预览：把图案平铺成一大片，显示无缝效果。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = np.zeros((64, 64), dtype=np.uint8)
        self.setMinimumSize(220, 220)

    def set_pattern(self, data: np.ndarray):
        self.data = data
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(255, 255, 255))

        n = self.data.shape[0]
        if n == 0:
            return
        tiles = 4
        avail = min(self.width(), self.height())
        cs = avail / (n * tiles)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(QColor(40, 40, 40)))
        for ty in range(tiles):
            for tx in range(tiles):
                for r in range(n):
                    for c in range(n):
                        if self.data[r, c] > 0:
                            x = tx * n * cs + c * cs
                            y = ty * n * cs + r * cs
                            painter.drawRect(QRectF(x, y, cs, cs))


class ScreentoneEditorDialog(QDialog):
    """手绘网点图案编辑器对话框。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr('Screentone Pattern Editor'))
        self.setModal(True)

        # ── 左侧: 网格画布 ─────────────────────────────────────────────
        self.canvas = PatternGridCanvas(64)
        canvas_group = QGroupBox(self.tr('Draw (seamless tile)'))
        canvas_layout = QVBoxLayout(canvas_group)
        canvas_layout.addWidget(self.canvas)

        ctrl_row = QHBoxLayout()
        ctrl_row.addWidget(QLabel(self.tr('Grid')))

        self.grid_combo = QComboBox()
        self.grid_combo.addItems([str(s) for s in GRID_SIZES])
        self.grid_combo.setCurrentIndex(GRID_SIZES.index(64))
        self.grid_combo.currentIndexChanged.connect(self._on_grid_changed)
        ctrl_row.addWidget(self.grid_combo)

        self.paint_btn = QPushButton(self.tr('Paint'))
        self.paint_btn.setCheckable(True)
        self.paint_btn.setChecked(True)
        self.paint_btn.clicked.connect(lambda: self._set_mode(True))
        ctrl_row.addWidget(self.paint_btn)

        self.erase_btn = QPushButton(self.tr('Erase'))
        self.erase_btn.setCheckable(True)
        self.erase_btn.clicked.connect(lambda: self._set_mode(False))
        ctrl_row.addWidget(self.erase_btn)

        self.clear_btn = QPushButton(self.tr('Clear'))
        self.clear_btn.clicked.connect(self.canvas.clear)
        ctrl_row.addWidget(self.clear_btn)

        ctrl_row.addStretch(-1)
        canvas_layout.addLayout(ctrl_row)

        # ── 右侧: 平铺预览 ─────────────────────────────────────────────
        self.preview = PatternPreviewWidget()
        preview_group = QGroupBox(self.tr('Tiling Preview'))
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.addWidget(self.preview)

        # ── 底部: 命名 + 保存 ──────────────────────────────────────────
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel(self.tr('Name')))
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText(self.tr('my_pattern'))
        name_row.addWidget(self.name_edit)
        name_row.addStretch(-1)

        self.save_btn = QPushButton(self.tr('Save'))
        self.save_btn.clicked.connect(self._save)
        self.cancel_btn = QPushButton(self.tr('Cancel'))
        self.cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch(-1)
        btn_row.addWidget(self.save_btn)
        btn_row.addWidget(self.cancel_btn)

        # ── 总布局 ─────────────────────────────────────────────────────
        main_row = QHBoxLayout()
        main_row.addWidget(canvas_group, stretch=2)
        main_row.addWidget(preview_group, stretch=1)

        layout = QVBoxLayout(self)
        layout.addLayout(main_row)
        layout.addLayout(name_row)
        layout.addLayout(btn_row)
        layout.setSizeConstraint(QDialog.SizeConstraint.SetFixedSize)

        # 画布变化 → 刷新预览
        self.canvas.pattern_changed.connect(self._update_preview)

        # 初始示例 + 预览
        self.canvas.data = self._make_sample_dots(64)
        self.preview.set_pattern(self.canvas.data)

    @staticmethod
    def _make_sample_dots(n: int) -> np.ndarray:
        """生成一个简单的圆点示例图案，方便用户上手。"""
        data = np.zeros((n, n), dtype=np.uint8)
        radius = n * 0.28
        cy = cx = n / 2.0
        yy, xx = np.mgrid[0:n, 0:n]
        dist = np.sqrt((yy - cy) ** 2 + (xx - cx) ** 2)
        data[dist <= radius] = 255
        return data

    def _on_grid_changed(self, idx: int):
        self.canvas.set_grid_size(GRID_SIZES[idx])
        self._update_preview()

    def _set_mode(self, paint: bool):
        self.paint_btn.setChecked(paint)
        self.erase_btn.setChecked(not paint)
        self.canvas.set_paint_mode(paint)

    def _update_preview(self):
        self.preview.set_pattern(self.canvas.data)

    def _save(self):
        name = self.name_edit.text().strip()
        if not name:
            name = 'pattern'
        if not name.lower().endswith('.png'):
            name += '.png'
        # 规范化文件名，去掉非法字符
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, '_')

        os.makedirs(C.SCREENTONE_DIR, exist_ok=True)
        path = osp.join(C.SCREENTONE_DIR, name)
        cv2.imwrite(path, self.canvas.data)
        self.accept()
