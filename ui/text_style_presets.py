from typing import List, Dict

from qtpy.QtWidgets import (
    QMenu, QMessageBox, QStackedLayout,
    QLineEdit, QSizePolicy, QHBoxLayout, QVBoxLayout, QPushButton,
    QLabel, QTabBar, QInputDialog, QApplication, QWidget
)
from qtpy.QtCore import Signal, Qt, QRectF, QPoint, QMimeData
from qtpy.QtGui import (
    QMouseEvent, QFontMetrics, QColor, QPixmap, QPainter,
    QContextMenuEvent, QDrag, QDragEnterEvent, QDropEvent, QDragMoveEvent
)

from utils.fontformat import FontFormat
from utils.config import save_text_styles, text_style_groups
from utils import config as C
from .custom_widget import PanelArea, Widget, FlowLayout


DEFAULT_GROUP_NAME = "默认"


class ArrowLeftButton(QPushButton):
    pass


class ArrowRightButton(QPushButton):
    pass


class DeleteStyleButton(QPushButton):
    pass


class StyleLabel(QLineEdit):

    edit_finished = Signal()

    def __init__(self, style_name: str = None, parent = None):
        super().__init__(parent=parent)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setStyleSheet("background-color: rgba(0, 0, 0, 0); border: none")
        self.setTextMargins(0, 0, 0, 0)
        self.setContentsMargins(0, 0, 0, 0)

        self.editingFinished.connect(self.edit_finished)
        self.setEnabled(False)

        if style_name is not None:
            self.setText(style_name)

        self.resizeToContent()
        self.edit_finished.connect(self.resizeToContent)

    def focusOutEvent(self, e) -> None:
        super().focusOutEvent(e)
        self.edit_finished.emit()

    def resizeToContent(self):
        fm = QFontMetrics(self.font())
        text = self.text()
        w = fm.boundingRect(text).width() + 5
        self.setFixedWidth(max(w, 32))


class TextStyleLabel(Widget):

    style_name_edited = Signal()
    delete_btn_clicked = Signal()
    stylelabel_activated = Signal(bool)
    apply_fontfmt = Signal(FontFormat)

    def __init__(self, style_name: str = '', parent: Widget = None, fontfmt: FontFormat = None, active_stylename_edited: Signal = None):
        super().__init__(parent=parent)
        self._double_clicked = False
        self.active = False
        self._drag_start_pos = None
        if fontfmt is None:
            if C.active_format is None:
                self.fontfmt = FontFormat()
            else:
                self.fontfmt = C.active_format.copy()
            self.fontfmt._style_name = style_name
        else:
            self.fontfmt = fontfmt
            style_name = fontfmt._style_name

        self.active_stylename_edited = active_stylename_edited
        self.stylelabel = StyleLabel(style_name, parent=self)
        self.stylelabel.edit_finished.connect(self.on_style_name_edited)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Maximum)

        self.setToolTip(self.tr('Click to set as Global format. Double click to edit name.'))
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        BTN_SIZE = 14
        self.colorw = colorw = QLabel(parent=self)
        self.colorw.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.colorw.setStyleSheet("border-radius: 7px; border: none; background-color: rgba(0, 0, 0, 0);")
        d = int(BTN_SIZE * 2)
        self.colorw.setFixedSize(d, d)

        self.apply_btn = ArrowLeftButton(parent=self)
        self.apply_btn.setFixedSize(d, BTN_SIZE)
        self.apply_btn.setToolTip(self.tr('Apply Text Style'))
        self.apply_btn.clicked.connect(self.on_applybtn_clicked)
        self.update_btn = ArrowRightButton(parent=self)
        self.update_btn.setFixedSize(d, BTN_SIZE)
        self.update_btn.clicked.connect(self.on_updatebtn_clicked)
        self.update_btn.setToolTip(self.tr('Update from active style'))
        applyw = Widget(parent=self)
        applyw.setStyleSheet("border-radius: 7px; border: none")
        applylayout = QVBoxLayout(applyw)
        applylayout.setSpacing(0)
        applylayout.setContentsMargins(0, 0, 0, 0)
        applylayout.addWidget(self.apply_btn)
        applylayout.addWidget(self.update_btn)

        self.leftstack = QStackedLayout()
        self.leftstack.setContentsMargins(0, 0, 0, 0)
        self.leftstack.addWidget(colorw)
        self.leftstack.addWidget(applyw)

        self.delete_btn = DeleteStyleButton(parent=self)
        dsize = BTN_SIZE // 3 * 2
        self.delete_btn.setFixedSize(dsize, dsize)
        self.delete_btn.setToolTip(self.tr("Delete Style"))
        self.delete_btn.clicked.connect(self.on_delete_btn_clicked)
        self.delete_btn.setStyleSheet("border: none")

        hlayout = QHBoxLayout(self)
        hlayout.setContentsMargins(0, 0, 3, 0)
        hlayout.setSpacing(0)
        hlayout.addLayout(self.leftstack)
        hlayout.addWidget(self.stylelabel)
        hlayout.addWidget(self.delete_btn)

        self.updatePreview()

    def on_delete_btn_clicked(self, *args, **kwargs):
        self.delete_btn_clicked.emit()

    def on_updatebtn_clicked(self, *args, **kwargs):
        self.update_style()

    def on_applybtn_clicked(self, *args, **kwargs):
        self.apply_fontfmt.emit(self.fontfmt)

    def update_style(self, fontfmt: FontFormat = None):
        if fontfmt is None:
            fontfmt = C.active_format
        if fontfmt is None:
            return
        updated_keys = self.fontfmt.merge(fontfmt, compare=True)
        if len(updated_keys) > 0:
            save_text_styles()

        preview_keys = {'font_family', 'frgb', 'srgb', 'stroke_width'}
        for k in updated_keys:
            if k in preview_keys:
                self.updatePreview()
                break

    def setActive(self, active: bool):
        self.active = active
        if active:
            self.setStyleSheet(
                "Widget {"
                "  background-color: rgba(30, 147, 229, 25%);"
                "  border: 2px solid rgb(30, 147, 229);"
                "  border-radius: 4px;"
                "}"
            )
        else:
            self.setStyleSheet(
                "Widget:hover {"
                "  background-color: rgba(30, 147, 229, 12%);"
                "}"
            )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_start_pos is not None:
            if (event.pos() - self._drag_start_pos).manhattanLength() > QApplication.startDragDistance():
                # 开始拖拽
                drag = QDrag(self)
                mime = QMimeData()
                mime.setText(self.fontfmt._style_name)
                drag.setMimeData(mime)
                pixmap = self.grab()
                drag.setPixmap(pixmap.scaled(self.size() * 0.8, Qt.KeepAspectRatio, Qt.SmoothTransformation))
                drag.setHotSpot(event.pos())
                self._drag_start_pos = None
                drag.exec_(Qt.MoveAction)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_pos = None
        if event.button() == Qt.MouseButton.LeftButton:
            if self._double_clicked:
                self._double_clicked = False
            else:
                active = not self.active
                self.setActive(active)
                self.stylelabel_activated.emit(active)
        return super().mouseReleaseEvent(event)

    def updatePreview(self):
        font = self.stylelabel.font()
        font.setFamily(self.fontfmt.font_family)
        self.stylelabel.setFont(font)

        d = int(self.colorw.width() * 0.66)
        radius = d / 2
        pixmap = QPixmap(d, d)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHints(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)

        draw_rect, draw_radius = QRectF(0, 0, d, d), radius
        if self.fontfmt.stroke_width > 0:
            r, g, b, *a = self.fontfmt.stroke_color()
            color = QColor(r, g, b, a[0] if a else 255)
            painter.setBrush(color)
            painter.drawRoundedRect(draw_rect, draw_radius, draw_radius)
            draw_radius = draw_radius * 0.66
            offset = d / 2 - draw_radius
            draw_rect = QRectF(offset, offset, draw_radius*2, draw_radius*2)

        r, g, b, *a = self.fontfmt.frgb
        color = QColor(r, g, b, a[0] if a else 255)
        painter.setBrush(color)
        painter.drawRoundedRect(draw_rect, draw_radius, draw_radius)
        painter.end()
        self.colorw.setPixmap(pixmap)

        self.stylelabel.resizeToContent()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        self._double_clicked = True
        self.startEdit()
        return super().mouseDoubleClickEvent(event)

    def startEdit(self, select_all=False):
        self.stylelabel.setEnabled(True)
        self.stylelabel.setFocus()
        self.setCursor(Qt.CursorShape.IBeamCursor)
        if select_all:
            self.stylelabel.selectAll()

    def enterEvent(self, event) -> None:
        self.leftstack.setCurrentIndex(1)
        self.delete_btn.setStyleSheet("image: url(icons/titlebar_close.svg); border: none")
        return super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.leftstack.setCurrentIndex(0)
        self.delete_btn.setStyleSheet("image: \"none\"; border: none")
        return super().leaveEvent(event)

    def on_style_name_edited(self):
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stylelabel.setEnabled(False)
        new_name = self.stylelabel.text()
        if self.fontfmt._style_name != new_name:
            self.fontfmt._style_name = new_name
            save_text_styles()

        if self.active and self.active_stylename_edited is not None:
            self.active_stylename_edited.emit()

        self._double_clicked = False


class TextAreaStyleButton(QPushButton):
    pass


class StyleTabPage(Widget):
    """单个标签页的内容：FlowLayout + 新建/删除按钮"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.flayout = FlowLayout()
        self.default_preset_name = self.tr('Style')

        self.new_btn = TextAreaStyleButton()
        self.new_btn.setObjectName("NewTextStyleButton")
        self.new_btn.setToolTip(self.tr("New Text Style"))

        self.clear_btn = TextAreaStyleButton()
        self.clear_btn.setObjectName("ClearTextStyleButton")
        self.clear_btn.setToolTip(self.tr("Remove All"))

        self.flayout.addWidget(self.new_btn)
        self.flayout.addWidget(self.clear_btn)

        vlayout = QVBoxLayout(self)
        vlayout.setContentsMargins(0, 0, 0, 0)
        vlayout.setSpacing(0)
        vlayout.addLayout(self.flayout, 1)

    def count(self):
        """返回样式数量（排除 new/clear 按钮）"""
        return max(0, self.flayout.count() - 2)

    def isEmpty(self):
        return self.count() < 1

    def _get_style_labels(self):
        """返回所有 TextStyleLabel 列表（排除按钮）"""
        labels = []
        for i in range(self.flayout.count()):
            item = self.flayout.itemAt(i)
            if item and isinstance(item.widget(), TextStyleLabel):
                labels.append(item.widget())
        return labels

    def _get_insert_idx(self, pos: QPoint) -> int:
        """根据 drop 位置确定插入索引"""
        labels = self._get_style_labels()
        if not labels:
            return 0

        # 找到最近的样式标签
        best_idx = len(labels)
        best_dist = float('inf')
        for i, lbl in enumerate(labels):
            center = lbl.geometry().center()
            dist = (pos - center).manhattanLength()
            if dist < best_dist:
                best_dist = dist
                if pos.x() > center.x():
                    best_idx = i + 1
                else:
                    best_idx = i
        return best_idx

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.source() and isinstance(event.source(), TextStyleLabel):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragMoveEvent):
        if event.source() and isinstance(event.source(), TextStyleLabel):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        source = event.source()
        if not source or not isinstance(source, TextStyleLabel):
            event.ignore()
            return

        # 找到源标签属于哪个页面（可能需要跨页移动？这里只处理同页）
        source_page = source.parent()
        if source_page is not self:
            # 跨标签页移动暂不支持
            event.ignore()
            return

        # 确定插入位置
        insert_idx = self._get_insert_idx(event.pos())
        current_idx = -1
        for i, lbl in enumerate(self._get_style_labels()):
            if lbl is source:
                current_idx = i
                break

        if current_idx < 0:
            event.ignore()
            return

        # 从布局中移除并重新插入
        source_idx_in_layout = -1
        for i in range(self.flayout.count()):
            item = self.flayout.itemAt(i)
            if item and item.widget() is source:
                source_idx_in_layout = i
                break

        if source_idx_in_layout < 0:
            event.ignore()
            return

        self.flayout.takeAt(source_idx_in_layout)

        # 计算新的插入位置（在 layout 中，排除按钮在末尾）
        btn_count = 2
        new_layout_idx = min(insert_idx, self.flayout.count() - btn_count)
        # 如果插入位置在当前索引后面，需要偏移1（因为移除了自己）
        if insert_idx > current_idx:
            pass  # 布局索引已经正确
        self.flayout.insertWidget(new_layout_idx, source)
        self.flayout.update()

        # 更新数据层
        styles = self._get_current_group_styles()
        if styles is not None:
            item = styles.pop(current_idx)
            styles.insert(min(insert_idx, len(styles)), item)
            save_text_styles()

        event.acceptProposedAction()

    def _get_current_group_styles(self) -> List[FontFormat]:
        """查找当前页面对应的样式列表"""
        parent_panel = self.parent_panel()
        if parent_panel:
            return parent_panel._current_tab_styles()
        return None

    def parent_panel(self):
        p = self.parent()
        while p is not None:
            if isinstance(p, TextStylePresetPanel):
                return p
            p = p.parent()
        return None


class TextStylePresetPanel(PanelArea):

    entered = False
    active_text_style_label_changed = Signal()
    apply_fontfmt = Signal(FontFormat)
    active_stylename_edited = Signal()
    export_style = Signal()
    import_style = Signal()

    def __init__(self, panel_name: str, config_name: str, config_expand_name: str):
        super().__init__(panel_name, config_name, config_expand_name)

        self.active_text_style_label: TextStyleLabel = None
        self.default_preset_name = self.tr('Style')
        self._tab_pages: List[StyleTabPage] = []

        # 主布局
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        # 标签栏
        self.tab_bar = QTabBar()
        self.tab_bar.setObjectName("StyleGroupTabBar")
        self.tab_bar.setMovable(True)
        self.tab_bar.setTabsClosable(False)
        self.tab_bar.setExpanding(False)
        self.tab_bar.setDocumentMode(True)
        self.tab_bar.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_bar.currentChanged.connect(self._on_tab_changed)
        self.tab_bar.tabBarDoubleClicked.connect(self._on_tab_double_clicked)
        self.tab_bar.customContextMenuRequested.connect(self._on_tab_context_menu)
        self.tab_bar.tabMoved.connect(self._on_tab_moved)

        # "+" 新建标签按钮
        self.add_tab_btn = QPushButton("+")
        self.add_tab_btn.setObjectName("StyleGroupAddButton")
        self.add_tab_btn.setFixedSize(28, 28)
        self.add_tab_btn.setToolTip(self.tr("New Group"))
        self.add_tab_btn.clicked.connect(self._add_tab)

        tab_layout = QHBoxLayout()
        tab_layout.setContentsMargins(0, 0, 0, 0)
        tab_layout.setSpacing(0)
        tab_layout.addWidget(self.tab_bar)
        tab_layout.addWidget(self.add_tab_btn)
        tab_layout.addStretch()

        # 堆叠布局
        self.stacked_layout = QStackedLayout()
        self.stacked_layout.setContentsMargins(0, 0, 0, 0)

        main_layout.addLayout(tab_layout)
        main_layout.addLayout(self.stacked_layout)
        self.setContentLayout(main_layout)

        # 初始化标签页
        self._init_from_groups()

    # ─── 标签页管理 ───

    def _init_from_groups(self):
        """从 text_style_groups 初始化标签页"""
        # 确保至少有一个组
        if not C.text_style_groups:
            C.text_style_groups.append({"name": DEFAULT_GROUP_NAME, "styles": []})

        for group in C.text_style_groups:
            self._add_tab_from_group(group["name"], group["styles"])

        if self.tab_bar.count() > 0:
            self.tab_bar.setCurrentIndex(0)

        self._update_tab_visibility()

    def _add_tab_from_group(self, name: str, styles: List[FontFormat] = None):
        """从组数据创建标签页"""
        page = StyleTabPage()
        page.new_btn.clicked.connect(self._on_page_new_btn_clicked)
        page.clear_btn.clicked.connect(self._on_page_clear_btn_clicked)

        # 添加已有样式
        if styles:
            for fmt in styles:
                self._add_style_label_to_page(page, fmt)

        self._tab_pages.append(page)
        self.stacked_layout.addWidget(page)
        tab_idx = self.tab_bar.addTab(name)

        # 连接 page 内标签的信号
        for label in page._get_style_labels():
            self._connect_label_signals(label)

        return page

    def _add_tab(self):
        """新建一个空白标签页"""
        name, ok = QInputDialog.getText(
            self, self.tr("New Style Group"),
            self.tr("Group name:"),
            text=self.tr("New Group")
        )
        if not ok or not name.strip():
            name = self.tr("New Group")

        # 去重
        existing = [self.tab_bar.tabText(i) for i in range(self.tab_bar.count())]
        if name.strip() in existing:
            base = name.strip()
            suffix = 2
            while f"{base} {suffix}" in existing:
                suffix += 1
            name = f"{base} {suffix}"

        new_group = {"name": name.strip(), "styles": []}
        C.text_style_groups.append(new_group)
        self._add_tab_from_group(name.strip(), [])
        self.tab_bar.setCurrentIndex(self.tab_bar.count() - 1)
        save_text_styles()

    def _on_tab_changed(self, idx: int):
        """切换标签页"""
        if 0 <= idx < self.stacked_layout.count():
            self.stacked_layout.setCurrentIndex(idx)
            self._resize_to_content()

    def _on_tab_double_clicked(self, idx: int):
        """双击标签重命名"""
        if idx < 0:
            return
        old_name = self.tab_bar.tabText(idx)
        new_name, ok = QInputDialog.getText(
            self, self.tr("Rename Group"),
            self.tr("New name:"),
            text=old_name
        )
        if ok and new_name.strip() and new_name.strip() != old_name:
            self.tab_bar.setTabText(idx, new_name.strip())
            if idx < len(C.text_style_groups):
                C.text_style_groups[idx]["name"] = new_name.strip()
                save_text_styles()

    def _on_tab_context_menu(self, pos: QPoint):
        """标签页右键菜单"""
        tab_idx = self.tab_bar.tabAt(pos)
        menu = QMenu()

        if tab_idx >= 0:
            rename_act = menu.addAction(self.tr("Rename Group"))
            delete_act = menu.addAction(self.tr("Delete Group"))
            menu.addSeparator()

        new_act = menu.addAction(self.tr("New Group"))

        rst = menu.exec_(self.tab_bar.mapToGlobal(pos))

        if tab_idx >= 0:
            if rst == rename_act:
                self._on_tab_double_clicked(tab_idx)
            elif rst == delete_act:
                self._delete_tab(tab_idx)
        if rst == new_act:
            self._add_tab()

    def _delete_tab(self, idx: int):
        """删除标签页"""
        if self.tab_bar.count() <= 1:
            QMessageBox.information(self, self.tr("Info"),
                                    self.tr("Cannot delete the last group."))
            return

        msg = QMessageBox()
        msg.setText(self.tr('Delete group "%s" and all its styles?') % self.tab_bar.tabText(idx))
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if msg.exec_() != QMessageBox.StandardButton.Yes:
            return

        # 清理 active label
        page = self._tab_pages[idx]
        for label in page._get_style_labels():
            if label.active:
                label.setActive(False)
                self.active_text_style_label = None
                self.active_text_style_label_changed.emit()
                break

        # 移除
        self.tab_bar.removeTab(idx)
        self.stacked_layout.removeWidget(page)
        self._tab_pages.pop(idx)
        if idx < len(C.text_style_groups):
            C.text_style_groups.pop(idx)

        page.deleteLater()
        self._update_tab_visibility()
        save_text_styles()

    def _on_tab_moved(self, from_idx: int, to_idx: int):
        """标签页拖动排序"""
        # 同步数据
        if from_idx < len(C.text_style_groups) and to_idx < len(C.text_style_groups):
            item = C.text_style_groups.pop(from_idx)
            C.text_style_groups.insert(to_idx, item)

        # 同步页面列表
        page = self._tab_pages.pop(from_idx)
        self._tab_pages.insert(to_idx, page)
        save_text_styles()

    # ─── 当前标签页样式管理 ───

    def _current_tab_page(self) -> StyleTabPage:
        idx = self.stacked_layout.currentIndex()
        if 0 <= idx < len(self._tab_pages):
            return self._tab_pages[idx]
        return None

    def _current_tab_styles(self) -> List[FontFormat]:
        """获取当前标签页对应的样式列表"""
        idx = self.tab_bar.currentIndex()
        if 0 <= idx < len(C.text_style_groups):
            return C.text_style_groups[idx]["styles"]
        return None

    def _on_page_new_btn_clicked(self):
        """当前标签页的"新建样式"按钮"""
        page = self._current_tab_page()
        if page is None:
            return
        label = self._new_textstyle_label_on_page(page)
        if label:
            label.startEdit(select_all=True)
            self._resize_to_content()

    def _on_page_clear_btn_clicked(self):
        """当前标签页的"清除全部"按钮"""
        page = self._current_tab_page()
        if page is None or page.isEmpty():
            return
        msg = QMessageBox()
        msg.setText(self.tr('Remove all styles in this group?'))
        msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if msg.exec_() == QMessageBox.StandardButton.Yes:
            self._clear_styles_on_page(page)

    def _new_textstyle_label_on_page(self, page: StyleTabPage, preset_name: str = None) -> TextStyleLabel:
        """在指定页面上创建新样式标签"""
        if preset_name is None:
            sno = str(page.count() + 1)
            if len(sno) < 2:
                preset_name = self.default_preset_name + ' ' + sno
            else:
                preset_name = self.default_preset_name + sno

        label = TextStyleLabel(preset_name, active_stylename_edited=self.active_stylename_edited)
        self._connect_label_signals(label)
        page.flayout.insertWidget(page.count(), label)

        styles = self._find_styles_for_page(page)
        if styles is not None:
            styles.append(label.fontfmt)
            save_text_styles()
        return label

    def _add_style_label_to_page(self, page: StyleTabPage, fontfmt: FontFormat):
        """向页面添加一个已有样式标签"""
        label = TextStyleLabel(fontfmt=fontfmt, active_stylename_edited=self.active_stylename_edited)
        self._connect_label_signals(label)
        page.flayout.insertWidget(page.count(), label)

    def _connect_label_signals(self, label: TextStyleLabel):
        """连接样式标签的信号"""
        label.delete_btn_clicked.connect(self._on_label_delete_clicked)
        label.stylelabel_activated.connect(self._on_label_activated)
        label.apply_fontfmt.connect(self.apply_fontfmt)

    def _on_label_delete_clicked(self):
        """删除某个样式"""
        label: TextStyleLabel = self.sender()
        page = label.parent()
        if not isinstance(page, StyleTabPage):
            return
        self._remove_label_from_page(page, label)

    def _on_label_activated(self, active: bool):
        """样式被点击激活/取消"""
        if self.active_text_style_label is not None:
            self.active_text_style_label.setActive(False)
            self.active_text_style_label = None
        if active:
            self.active_text_style_label = self.sender()
        self.active_text_style_label_changed.emit()

    def _remove_label_from_page(self, page: StyleTabPage, label: TextStyleLabel):
        """从页面移除样式标签"""
        for i, item in enumerate(page.flayout._items):
            if item.widget() is label:
                if label is self.active_text_style_label:
                    label.setActive(False)
                    self.active_text_style_label = None
                    self.active_text_style_label_changed.emit()
                page.flayout.takeAt(i)
                page.flayout.update()
                self._update_tab_visibility()

                styles = self._find_styles_for_page(page)
                if styles is not None and i < len(styles):
                    styles.pop(i)
                    save_text_styles()
                label.deleteLater()
                self._resize_to_content()
                break

    def _clear_styles_on_page(self, page: StyleTabPage):
        """清除页面上的所有样式"""
        for label in page._get_style_labels():
            if label.active:
                label.setActive(False)
                self.active_text_style_label = None
                self.active_text_style_label_changed.emit()
            label.deleteLater()

        # 清空 layout 中的样式 widget
        i = 0
        while i < page.flayout.count():
            item = page.flayout.itemAt(i)
            if item and isinstance(item.widget(), TextStyleLabel):
                page.flayout.takeAt(i)
            else:
                i += 1

        page.flayout.update()
        styles = self._find_styles_for_page(page)
        if styles is not None:
            styles.clear()
            save_text_styles()
        self._update_tab_visibility()

    def _find_styles_for_page(self, page: StyleTabPage) -> List[FontFormat]:
        """查找页面在 text_style_groups 中对应的 styles 列表"""
        for idx, p in enumerate(self._tab_pages):
            if p is page:
                if idx < len(C.text_style_groups):
                    return C.text_style_groups[idx]["styles"]
                break
        return None

    # ─── 公共接口 ───

    def count(self):
        page = self._current_tab_page()
        return page.count() if page else 0

    def isEmpty(self):
        page = self._current_tab_page()
        return page is None or page.isEmpty()

    def initStyles(self, styles: List[FontFormat]):
        """兼容旧接口：扁平样式列表 → 包裹到默认组"""
        self._clear_all()
        C.text_style_groups.clear()
        C.text_style_groups.append({"name": DEFAULT_GROUP_NAME, "styles": list(styles)})
        self._init_from_groups()
        self._update_tab_visibility()
        self._resize_to_content()

    def setStyles(self, styles: List[FontFormat], save_styles_flag=False):
        """兼容旧接口：用扁平列表替换当前组"""
        page = self._current_tab_page()
        if page is None:
            return
        self._clear_styles_on_page(page)
        for fmt in styles:
            self._add_style_label_to_page(page, fmt)
        current_styles = self._current_tab_styles()
        if current_styles is not None:
            styles_copy = list(styles)
            current_styles.clear()
            current_styles.extend(styles_copy)
        self._update_tab_visibility()
        self._resize_to_content()
        if save_styles_flag:
            save_text_styles()

    def initGroups(self, groups: List[Dict]):
        """新接口：用分组数据初始化"""
        self._clear_all()
        # 必须先复制，因为 groups 可能与 C.text_style_groups 是同一对象
        groups_copy = list(groups)
        C.text_style_groups.clear()
        C.text_style_groups.extend(groups_copy)
        self._init_from_groups()
        self._update_tab_visibility()
        self._resize_to_content()

    def setGroups(self, groups: List[Dict], save_styles_flag=False):
        """新接口：替换全部分组数据"""
        self._clear_all()
        groups_copy = list(groups)
        C.text_style_groups.clear()
        C.text_style_groups.extend(groups_copy)
        self._init_from_groups()
        self._update_tab_visibility()
        self._resize_to_content()
        if save_styles_flag:
            save_text_styles()

    def _clear_all(self):
        """清除所有标签页"""
        self.active_text_style_label = None
        for page in self._tab_pages:
            self.stacked_layout.removeWidget(page)
            page.deleteLater()
        self._tab_pages.clear()
        while self.tab_bar.count() > 0:
            self.tab_bar.removeTab(0)

    # ─── 界面辅助 ───

    def _resize_to_content(self):
        TABBAR_HEIGHT = 30  # 标签栏占用的高度补偿
        TEXTSTYLEAREA_MAXH = 280
        page = self._current_tab_page()
        if page:
            h = page.flayout.heightForWidth(self.width())
            total_h = h + TABBAR_HEIGHT
            self.setFixedHeight(max(60, min(TEXTSTYLEAREA_MAXH, total_h)))
        else:
            self.setFixedHeight(50)

    def resizeEvent(self, e):
        self._resize_to_content()
        return super().resizeEvent(e)

    def _update_tab_visibility(self):
        """更新按钮可见性"""
        page = self._current_tab_page()
        if page is None:
            return
        has_styles = not page.isEmpty()
        self.add_tab_btn.setVisible(True)
        if has_styles or self.entered:
            page.new_btn.show()
            page.clear_btn.show()
        else:
            page.new_btn.hide()
            page.clear_btn.hide()

    def enterEvent(self, event) -> None:
        self.entered = True
        self._update_tab_visibility()
        return super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.entered = False
        page = self._current_tab_page()
        if page and not page.isEmpty():
            page.new_btn.hide()
            page.clear_btn.hide()
        return super().leaveEvent(event)

    def clearStyles(self):
        """清空当前组的所有样式"""
        page = self._current_tab_page()
        if page and not page.isEmpty():
            self._clear_styles_on_page(page)

    def contextMenuEvent(self, e: QContextMenuEvent):
        menu = QMenu()

        new_act = menu.addAction(self.tr('New Text Style'))
        removeall_act = menu.addAction(self.tr('Remove all'))
        menu.addSeparator()
        import_act = menu.addAction(self.tr('Import Text Styles'))
        export_act = menu.addAction(self.tr('Export Text Styles'))

        rst = menu.exec_(e.globalPos())

        if rst == new_act:
            self._on_page_new_btn_clicked()
        elif rst == removeall_act:
            self._on_page_clear_btn_clicked()
        elif rst == import_act:
            self.import_style.emit()
        elif rst == export_act:
            self.export_style.emit()

        return super().contextMenuEvent(e)
