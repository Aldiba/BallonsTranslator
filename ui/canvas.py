import numpy as np
from typing import List, Union
import os

from qtpy.QtWidgets import QApplication, QSlider, QMenu, QGraphicsScene, QGraphicsSceneDragDropEvent , QGraphicsView, QGraphicsSceneDragDropEvent, QGraphicsRectItem, QGraphicsItem, QScrollBar, QGraphicsPixmapItem, QGraphicsSceneMouseEvent, QGraphicsSceneContextMenuEvent, QRubberBand, QGraphicsLineItem, QGraphicsPathItem, QGraphicsEllipseItem
from qtpy.QtCore import Qt, QDateTime, QRectF, QPointF, QPoint, Signal, QSizeF, QEvent
from qtpy.QtGui import QKeySequence, QPixmap, QImage, QHideEvent, QKeyEvent, QWheelEvent, QResizeEvent, QPainter, QPen, QPainterPath, QCursor, QNativeGestureEvent, QColor

try:
    from qtpy.QtWidgets import QUndoStack, QUndoCommand
except:
    from qtpy.QtGui import QUndoStack, QUndoCommand

from .misc import ndarray2pixmap, QKEY, QNUMERIC_KEYS, ARROWKEY2DIRECTION
from .textitem import TextBlkItem, TextBlock
from .texteditshapecontrol import TextBlkShapeControl
from .custom_widget import ScrollBar, FadeLabel
from .image_edit import ImageEditMode, DrawingLayer, StrokeImgItem, CloneStampItem
from .page_search_widget import PageSearchWidget
from utils import shared as C
from utils.config import pcfg
from utils.proj_imgtrans import ProjImgTrans

CANVAS_SCALE_MAX = 10.0
CANVAS_SCALE_MIN = 0.01
CANVAS_SCALE_SPEED = 0.1
CANVAS_SCENE_MARGIN = 150  # 动态边距基础值（像素），会根据缩放级别自动调整

class MoveByKeyCommand(QUndoCommand):
    def __init__(self, blkitems: List[TextBlkItem], direction: QPointF, shape_ctrl: TextBlkShapeControl) -> None:
        super().__init__()
        self.blkitems = blkitems
        self.direction = direction
        self.ori_pos_list = []
        self.end_pos_list = []
        self.shape_ctrl = shape_ctrl
        for blk in blkitems:
            pos = blk.pos()
            self.ori_pos_list.append(pos)
            self.end_pos_list.append(pos + direction)

    def undo(self):
        for blk, pos in zip(self.blkitems, self.ori_pos_list):
            blk.setPos(pos)
            if blk.under_ctrl and self.shape_ctrl.blk_item == blk:
                self.shape_ctrl.updateBoundingRect()

    def redo(self):
        for blk, pos in zip(self.blkitems, self.end_pos_list):
            blk.setPos(pos)
            if blk.under_ctrl and self.shape_ctrl.blk_item == blk:
                self.shape_ctrl.updateBoundingRect()

    def mergeWith(self, other: QUndoCommand) -> bool:
        canmerge = self.blkitems == other.blkitems and self.direction == other.direction
        if canmerge:
            self.end_pos_list = other.end_pos_list
        return canmerge
    
    def id(self):
        return 1


class CustomGV(QGraphicsView):
    ctrl_pressed = False
    scale_up_signal = Signal()
    scale_down_signal = Signal()
    scale_with_value = Signal(float)
    view_resized = Signal()
    hide_canvas = Signal()
    ctrl_released = Signal()
    canvas: QGraphicsScene = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scrollbar_h = ScrollBar(Qt.Orientation.Horizontal, self, fadeout=True)
        self.scrollbar_v = ScrollBar(Qt.Orientation.Vertical, self, fadeout=True)

        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)

    def wheelEvent(self, event : QWheelEvent) -> None:
        # qgraphicsview always scroll content according to wheelevent
        # which is not desired when scaling img
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            if event.angleDelta().y() > 0:
                self.scale_up_signal.emit()
            else:
                self.scale_down_signal.emit()
            return
        return super().wheelEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.key() == QKEY.Key_Control:
            self.ctrl_pressed = False
            self.ctrl_released.emit()
        # Shift+拖拽画直线：Shift释放时取消画线状态
        if event.key() == Qt.Key.Key_Shift and self.canvas.shift_line_start is not None:
            self.canvas.shift_line_start = None
            self.canvas._remove_line_preview()
        return super().keyReleaseEvent(event)

    def keyPressEvent(self, e: QKeyEvent) -> None:
        key = e.key()
        if key == QKEY.Key_Control:
            self.ctrl_pressed = True

        modifiers = e.modifiers()
        if modifiers == Qt.KeyboardModifier.ControlModifier:
            if key == QKEY.Key_V:
                # self.ctrlv_pressed.emit(e)
                if self.canvas.handle_ctrlv():
                    e.accept()
                    return
            if key == QKEY.Key_C:
                if self.canvas.handle_ctrlc():
                    e.accept()
                    return
                
        elif modifiers & Qt.KeyboardModifier.ControlModifier and modifiers & Qt.KeyboardModifier.ShiftModifier:
            if key == QKEY.Key_C:
                self.canvas.copy_src_signal.emit()
                e.accept()
                return
            elif key == QKEY.Key_V:
                self.canvas.paste_src_signal.emit()
                e.accept()
                return
            elif key == QKEY.Key_D:
                self.canvas.delete_textblks.emit(1)
                e.accept()
                return

        return super().keyPressEvent(e)

    def resizeEvent(self, event: QResizeEvent) -> None:
        self.view_resized.emit()
        return super().resizeEvent(event)

    def hideEvent(self, event: QHideEvent) -> None:
        self.hide_canvas.emit()
        return super().hideEvent(event)

    def event(self, e):
        if isinstance(e, QNativeGestureEvent):
            if e.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self.scale_with_value.emit(e.value() + 1)
                e.setAccepted(True)

        return super().event(e)
    
    def dragMoveEvent(self, e: QGraphicsSceneDragDropEvent):
        super().dragMoveEvent(e)
        if e.mimeData().hasUrls():
            # issue #908, https://stackoverflow.com/questions/4177720/accepting-drops-on-a-qgraphicsscene
            e.setAccepted(True)


class Canvas(QGraphicsScene):

    scalefactor_changed = Signal()
    end_create_textblock = Signal(QRectF)
    paste2selected_textitems = Signal()
    end_create_rect = Signal(QRectF, int)
    finish_painting = Signal(QGraphicsItem)
    finish_erasing = Signal(QGraphicsItem)
    delete_textblks = Signal(int)
    copy_textblks = Signal()
    paste_textblks = Signal(QPointF)
    copy_src_signal = Signal()
    paste_src_signal = Signal()

    format_textblks = Signal()
    layout_textblks = Signal()
    reset_angle = Signal()
    squeeze_blk = Signal()

    run_blktrans = Signal(int)

    begin_scale_tool = Signal(QPointF)
    scale_tool = Signal(QPointF)
    end_scale_tool = Signal()
    canvas_undostack_changed = Signal()
    
    imgtrans_proj: ProjImgTrans = None
    painting_pen = QPen()
    painting_shape = 0
    erasing_pen = QPen()
    image_edit_mode = ImageEditMode.NONE

    projstate_unsaved = False
    proj_savestate_changed = Signal(bool)
    textstack_changed = Signal()
    drop_open_folder = Signal(str)
    context_menu_requested = Signal(QPoint, bool)
    incanvas_selection_changed = Signal()
    switch_text_item = Signal(int, QKeyEvent)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scale_factor = 1.
        self.text_transparency = 0
        self.textblock_mode = False
        self.creating_textblock = False
        self.create_block_origin: QPointF = None
        self.editing_textblkitem: TextBlkItem = None

        self.gv = CustomGV(self)
        self.gv.scale_down_signal.connect(self.scaleDown)
        self.gv.scale_up_signal.connect(self.scaleUp)
        self.gv.scale_with_value.connect(self.scaleBy)
        self.gv.view_resized.connect(self.onViewResized)
        self.gv.hide_canvas.connect(self.on_hide_canvas)
        self.gv.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.gv.canvas = self
        self.gv.setAcceptDrops(True)
        self.gv.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.gv.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.context_menu_requested.connect(self.on_create_contextmenu)
        
        if not C.FLAG_QT6:
            # mitigate https://bugreports.qt.io/browse/QTBUG-93417
            # produce blurred result, saving imgs remain unaffected
            self.gv.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        self.search_widget = PageSearchWidget(self.gv)
        self.search_widget.hide()
        
        self.ctrl_relesed = self.gv.ctrl_released
        self.vscroll_bar = self.gv.verticalScrollBar()
        self.hscroll_bar = self.gv.horizontalScrollBar()
        # self.default_cursor = self.gv.cursor()
        self.rubber_band = self.addWidget(QRubberBand(QRubberBand.Shape.Rectangle))
        self.rubber_band.hide()
        self.rubber_band_origin = None

        self.draw_undo_stack = QUndoStack(self)
        self.text_undo_stack = QUndoStack(self)
        self.saved_drawundo_step = 0
        self.saved_textundo_step = 0

# Shift+拖拽画直线功能
        self.shift_line_start: QPointF = None  # 直线起点
        self.shift_line_preview: QGraphicsPathItem = None  # 预览线（两条平行线）

        self.scaleFactorLabel = FadeLabel(self.gv)
        self.scaleFactorLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.scaleFactorLabel.setText('100%')
        self.scaleFactorLabel.gv = self.gv

        self.txtblkShapeControl = TextBlkShapeControl(self.gv)
        
        self.baseLayer = QGraphicsRectItem()
        pen = QPen()
        pen.setColor(Qt.GlobalColor.transparent)
        self.baseLayer.setPen(pen)

        self.inpaintLayer = QGraphicsPixmapItem()
        self.inpaintLayer.setTransformationMode(Qt.TransformationMode.SmoothTransformation)
        self.drawingLayer = DrawingLayer()
        self.drawingLayer.setTransformationMode(Qt.TransformationMode.FastTransformation)
        self.textLayer = QGraphicsPixmapItem()

        self.inpaintLayer.setAcceptDrops(True)
        self.drawingLayer.setAcceptDrops(True)
        self.textLayer.setAcceptDrops(True)
        self.baseLayer.setAcceptDrops(True)
        
        self.base_pixmap: QPixmap = None

        self.addItem(self.baseLayer)
        self.inpaintLayer.setParentItem(self.baseLayer)
        self.drawingLayer.setParentItem(self.baseLayer)
        self.textLayer.setParentItem(self.baseLayer)
        self.txtblkShapeControl.setParentItem(self.baseLayer)

        self.scalefactor_changed.connect(self.onScaleFactorChanged)
        self.selectionChanged.connect(self.on_selection_changed)     

        self.stroke_img_item: StrokeImgItem = None
        self.erase_img_key = None

        # Clone stamp state
        self.clone_source: QPointF = None
        self.clone_source_item: QGraphicsEllipseItem = None
        self.clone_stamp_item: CloneStampItem = None
        self.clone_preview_item: QGraphicsPixmapItem = None
        self._clone_preview_pixmap: QPixmap = None
        self._clone_last_src_scene: QPointF = None

        self.editor_index = 0 # 0: drawing 1: text editor
        self.mid_btn_pressed = False
        self.pan_initial_pos = QPoint(0, 0)

        self.saved_textundo_step = 0
        self.saved_drawundo_step = 0
        self.num_pushed_textstep = 0
        self.num_pushed_drawstep = 0

        self.clipboard_blks: List[TextBlock] = []

        self.drop_folder: str = None
        self.block_selection_signal = False
        
        im_rect = QRectF(0, 0, C.SCREEN_W, C.SCREEN_H)
        self.baseLayer.setRect(im_rect)

        self.textlayer_trans_slider: QSlider = None
        self.originallayer_trans_slider: QSlider = None

    def on_switch_item(self, switch_delta: int, key_event: QKeyEvent = None):
        if self.textEditMode():
            self.switch_text_item.emit(switch_delta, key_event)

    def img_window_size(self):
        if self.imgtrans_proj.inpainted_valid:
            return self.inpaintLayer.pixmap().size()
        return self.baseLayer.rect().size().toSize()

    def dragEnterEvent(self, e: QGraphicsSceneDragDropEvent):
        
        self.drop_folder = None
        if e.mimeData().hasUrls():
            urls = e.mimeData().urls()
            ufolder = None
            for url in urls:
                furl = url.toLocalFile()
                if os.path.isdir(furl):
                    ufolder = furl
                    break
            if ufolder is not None:
                e.acceptProposedAction()
                self.drop_folder = ufolder

    def dropEvent(self, event) -> None:
        if self.drop_folder is not None:
            self.drop_open_folder.emit(self.drop_folder)
            self.drop_folder = None
        return super().dropEvent(event)

    def textEditMode(self) -> bool:
        return self.editor_index == 1

    def drawMode(self) -> bool:
        return self.editor_index == 0

    def scaleUp(self):
        self.scaleImage(1 + CANVAS_SCALE_SPEED)

    def scaleDown(self):
        self.scaleImage(1 - CANVAS_SCALE_SPEED)

    def scaleBy(self, value: float):
        self.scaleImage(value)

    def _set_scene_scale(self, scale: float):
        self.scale_factor = scale
        self.baseLayer.setScale(scale)
        # 动态边距：缩放比例越大，边距越大，允许视角移动到边界外
        margin = int(CANVAS_SCENE_MARGIN * scale)
        base_w = self.baseLayer.sceneBoundingRect().width()
        base_h = self.baseLayer.sceneBoundingRect().height()
        self.setSceneRect(-margin, -margin, base_w + margin * 2, base_h + margin * 2)

    def render_result_img(self):

        self.inpaintLayer.hide()
        tlayer_opacity_before = self.textLayer.opacity()
        tlayer_visible = self.textLayer.isVisible()
        if tlayer_opacity_before != 1:
            self.textLayer.setOpacity(1)
        if not tlayer_visible:
            self.textLayer.show()
        scale_before = self.scale_factor
        if scale_before != 1:
            hb_pos = self.hscroll_bar.value()
            vb_pos = self.vscroll_bar.value()
            self._set_scene_scale(1)

        self.clearSelection()
        if self.textEditMode() and self.txtblkShapeControl.blk_item is not None:
            blk_item = self.txtblkShapeControl.blk_item
            if blk_item.is_editting():
                blk_item.endEdit(keep_focus=False)
            if blk_item.isSelected():
                blk_item.setSelected(False)

        result = ndarray2pixmap(self.imgtrans_proj.inpainted_array, return_qimg=True)
        canvas_sz = self.img_window_size()
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(0, 0, canvas_sz.width(), canvas_sz.height())
        self.render(painter, rect, rect)   #  produce blurred result if target/source rect not specified #320
        painter.end()

        if tlayer_opacity_before != 1:
            self.textLayer.setOpacity(tlayer_opacity_before)
        if not tlayer_visible:
            self.textLayer.hide()
        if scale_before != 1:
            self._set_scene_scale(scale_before)
            if self.hscroll_bar.value() != hb_pos:
                self.hscroll_bar.setValue(hb_pos)
            if self.vscroll_bar.value() != vb_pos:
                self.vscroll_bar.setValue(vb_pos)
        self.inpaintLayer.show()

        return result
    
    def updateLayers(self):
        
        if not self.imgtrans_proj.img_valid:
            return
        
        inpainted_as_base = self.imgtrans_proj.inpainted_valid
        
        if inpainted_as_base:
            self.base_pixmap = ndarray2pixmap(self.imgtrans_proj.inpainted_array)

        pixmap = self.base_pixmap.copy()
        painter = QPainter(pixmap)
        origin = QPoint(0, 0)

        if self.imgtrans_proj.img_valid and pcfg.original_transparency > 0:
            painter.setOpacity(pcfg.original_transparency)
            if inpainted_as_base:
                painter.drawPixmap(origin, ndarray2pixmap(self.imgtrans_proj.img_array))
            else:
                painter.drawPixmap(origin, pixmap)

        if self.imgtrans_proj.mask_valid and pcfg.mask_transparency > 0 and not self.textEditMode():
            painter.setOpacity(pcfg.mask_transparency)
            painter.drawPixmap(origin, ndarray2pixmap(self.imgtrans_proj.mask_array))

        # # 修复：合并 drawingLayer 到 inpaintLayer，使画笔内容能被 inpaint 操作
        # if self.drawingLayer.drawed():
        #     painter.drawPixmap(origin, self.drawingLayer.get_drawed_pixmap())

        painter.end()
        self.inpaintLayer.setPixmap(pixmap)

    def setMaskTransparency(self, transparency: float):
        pcfg.mask_transparency = transparency
        self.updateLayers()

    def setOriginalTransparency(self, transparency: float):
        pcfg.original_transparency = transparency
        self.updateLayers()

    def setTextLayerTransparency(self, transparency: float):
        self.textLayer.setOpacity(transparency)
        self.text_transparency = transparency

    def adjustScrollBar(self, scrollBar: QScrollBar, factor: float):
        scrollBar.setValue(int(factor * scrollBar.value() + ((factor - 1) * scrollBar.pageStep() / 2)))

    def scaleImage(self, factor: float):
        if not self.gv.isVisible() or not self.imgtrans_proj.img_valid:
            return
        s_f = self.scale_factor * factor
        s_f = np.clip(s_f, CANVAS_SCALE_MIN, CANVAS_SCALE_MAX)

        scale_changed = self.scale_factor != s_f
        self.scale_factor = s_f
        self.baseLayer.setScale(self.scale_factor)
        self.txtblkShapeControl.updateScale(self.scale_factor)

        if scale_changed:
            self.adjustScrollBar(self.gv.horizontalScrollBar(), factor)
            self.adjustScrollBar(self.gv.verticalScrollBar(), factor)
            self.scalefactor_changed.emit()
        # 动态边距：缩放比例越大，边距越大，允许视角移动到边界外
        margin = int(CANVAS_SCENE_MARGIN * self.scale_factor)
        base_w = self.baseLayer.sceneBoundingRect().width()
        base_h = self.baseLayer.sceneBoundingRect().height()
        self.setSceneRect(-margin, -margin, base_w + margin * 2, base_h + margin * 2)

    def onViewResized(self):
        gv_w, gv_h = self.gv.geometry().width(), self.gv.geometry().height()

        x = gv_w - self.scaleFactorLabel.width()
        y = gv_h - self.scaleFactorLabel.height()
        pos_new = (QPointF(x, y) / 2).toPoint()
        if self.scaleFactorLabel.pos() != pos_new:
            self.scaleFactorLabel.move(pos_new)
        
        x = gv_w - self.search_widget.width()
        pos = self.search_widget.pos()
        pos.setX(x-30)
        self.search_widget.move(pos)
        
    def onScaleFactorChanged(self):
        self.scaleFactorLabel.setText(f'{self.scale_factor*100:2.0f}%')
        self.scaleFactorLabel.raise_()
        self.scaleFactorLabel.startFadeAnimation()

    def on_selection_changed(self):
        if self.txtblkShapeControl.isVisible():
            blk_item = self.txtblkShapeControl.blk_item
            if blk_item is not None and blk_item.isEditing():
                blk_item.endEdit()
        if self.hasFocus() and not self.block_selection_signal:
            self.incanvas_selection_changed.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()

        modifiers = event.modifiers()
        if (modifiers == Qt.KeyboardModifier.AltModifier) and \
            not key == QKEY.Key_Alt and \
                self.editing_textblkitem is None:
            if key in {QKEY.Key_W, QKEY.Key_A, QKEY.Key_Left, QKEY.Key_Up}:
                self.on_switch_item(-1, event)
                return
            elif key in {QKEY.Key_S, QKEY.Key_D, QKEY.Key_Right, QKEY.Key_Down}:
                self.on_switch_item(1, event)
                return

        if self.editing_textblkitem is not None:
            return super().keyPressEvent(event)
        elif key in ARROWKEY2DIRECTION:
            sel_blkitems = self.selected_text_items()
            if len(sel_blkitems) > 0:
                direction = ARROWKEY2DIRECTION[key]
                cmd = MoveByKeyCommand(sel_blkitems, direction, self.txtblkShapeControl)
                self.push_undo_command(cmd)
                event.setAccepted(True)
                return
        elif key in QNUMERIC_KEYS:
            value = QNUMERIC_KEYS[key]
            self.set_active_layer_transparency(value * 10)
        return super().keyPressEvent(event)
    
    def set_active_layer_transparency(self, value: int):
        if self.textEditMode():
            opacity = self.textLayer.opacity() * 100
            if value == 0 and opacity == 0:
                value = 100
            self.textlayer_trans_slider.setValue(value)
            self.originallayer_trans_slider.setValue(100 - value)
            self.updateLayers()

    def addStrokeImageItem(self, pos: QPointF, pen: QPen, erasing: bool = False):
        if self.stroke_img_item is not None:
            self.stroke_img_item.startNewPoint(pos)
        else:
            self.stroke_img_item = StrokeImgItem(pen, pos, self.img_window_size(), shape=self.painting_shape)
            if not erasing:
                self.stroke_img_item.setParentItem(self.baseLayer)
            else:
                self.erase_img_key = str(QDateTime.currentMSecsSinceEpoch())
                compose_mode = QPainter.CompositionMode.CompositionMode_DestinationOut
                self.drawingLayer.addQImage(0, 0, self.stroke_img_item._img, compose_mode, self.erase_img_key)

    def drawLineBetweenPoints(self, start: QPointF, end: QPointF):
        """Shift+拖拽画直线：从start到end画一条直线"""
        # 转换为 inpaintLayer 本地坐标（与普通绘制保持一致）
        start_local = self.inpaintLayer.mapFromScene(start)
        end_local = self.inpaintLayer.mapFromScene(end)
        # 创建 StrokeImgItem，从起点开始
        self.stroke_img_item = StrokeImgItem(self.painting_pen, start_local, self.img_window_size(), shape=self.painting_shape)
        self.stroke_img_item.setParentItem(self.baseLayer)
        # 调用 lineTo 画到终点
        self.stroke_img_item.lineTo(end_local)
        # 完成绘制
        self.stroke_img_item.finishPainting()
        # 触发 finish_painting 信号，交给 drawingpanel 处理撤销等
        self.finish_painting.emit(self.stroke_img_item)
        self.stroke_img_item = None

    def _create_line_preview(self, start_scene: QPointF):
        """创建直线预览（使用scene坐标，两条平行线表示笔刷宽度）"""
        if self.shift_line_preview is None:
            self.shift_line_preview = QGraphicsPathItem()
            pen = QPen()
            pen.setColor(QColor(0, 255, 255, 180))  # 青色带透明度
            pen.setWidthF(1.5 / max(self.scale_factor, 0.01))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setDashPattern([6, 4])
            self.shift_line_preview.setPen(pen)
            self.shift_line_preview.setZValue(999)
            self.shift_line_preview.setParentItem(self.baseLayer)

    def _update_line_preview(self, end_scene: QPointF):
        """更新直线预览（使用baseLayer本地坐标，正确跟随缩放）"""
        if self.shift_line_preview is not None and self.shift_line_start is not None:
            path = QPainterPath()

            # 转换为 baseLayer 本地坐标，使预览在缩放时保持一致
            start_bl = self.baseLayer.mapFromScene(self.shift_line_start)
            end_bl = self.baseLayer.mapFromScene(end_scene)

            # 计算垂直于线段的偏移方向
            dx = end_bl.x() - start_bl.x()
            dy = end_bl.y() - start_bl.y()
            length = (dx * dx + dy * dy) ** 0.5
            if length < 1:
                # 起点画笔刷形状
                self._add_brush_shape_to_path(path, start_bl)
                self.shift_line_preview.setPath(path)
                return

            # 法向量（垂直方向）
            nx = -dy / length
            ny = dx / length
            brush_half = self.painting_pen.widthF() / 2

            # 两条平行线的起点和终点
            x1 = start_bl.x() + nx * brush_half
            y1 = start_bl.y() + ny * brush_half
            x2 = end_bl.x() + nx * brush_half
            y2 = end_bl.y() + ny * brush_half
            x3 = start_bl.x() - nx * brush_half
            y3 = start_bl.y() - ny * brush_half
            x4 = end_bl.x() - nx * brush_half
            y4 = end_bl.y() - ny * brush_half

            # 绘制两条平行线
            path.moveTo(x1, y1)
            path.lineTo(x2, y2)
            path.moveTo(x3, y3)
            path.lineTo(x4, y4)

            # 起点画笔刷形状
            self._add_brush_shape_to_path(path, start_bl)

            self.shift_line_preview.setPath(path)

    def _add_brush_shape_to_path(self, path: QPainterPath, center: QPointF):
        """在路径中添加笔刷形状（baseLayer本地坐标，自动匹配缩放）"""
        brush_size = self.painting_pen.widthF()
        half = brush_size / 2
        if self.painting_shape == 0:  # Circle
            path.addEllipse(center.x() - half, center.y() - half, brush_size, brush_size)
        else:  # Rectangle
            path.addRect(center.x() - half, center.y() - half, brush_size, brush_size)

    def _remove_line_preview(self):
        """移除直线预览"""
        if self.shift_line_preview is not None:
            self.removeItem(self.shift_line_preview)
            self.shift_line_preview = None

    def startCreateTextblock(self, pos: QPointF, hide_control: bool = False):
        pos = pos / self.scale_factor
        self.creating_textblock = True
        self.create_block_origin = pos
        self.gv.setCursor(Qt.CursorShape.CrossCursor)
        self.txtblkShapeControl.setBlkItem(None)
        self.txtblkShapeControl.setPos(0, 0)
        self.txtblkShapeControl.setRotation(0)
        self.txtblkShapeControl.setRect(QRectF(pos, QSizeF(1, 1)))
        if hide_control:
            self.txtblkShapeControl.hideControls()
        self.txtblkShapeControl.show()

    def endCreateTextblock(self, btn=0):
        self.creating_textblock = False
        self.gv.setCursor(Qt.CursorShape.ArrowCursor)
        self.txtblkShapeControl.hide()
        textblk_created = False
        rect = self.txtblkShapeControl.rect()
        if self.creating_normal_rect:
            self.end_create_rect.emit(rect, btn)
            self.txtblkShapeControl.showControls()
        else:
            if rect.width() > 1 and rect.height() > 1:
                self.end_create_textblock.emit(rect)
                textblk_created = True
        return textblk_created

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if self.mid_btn_pressed:
            new_pos = event.screenPos()
            delta_pos = new_pos - self.pan_initial_pos
            self.pan_initial_pos = new_pos
            self.hscroll_bar.setValue(int(self.hscroll_bar.value() - delta_pos.x()))
            self.vscroll_bar.setValue(int(self.vscroll_bar.value() - delta_pos.y()))
            
        elif self.creating_textblock:
            self.txtblkShapeControl.setRect(QRectF(self.create_block_origin, event.scenePos() / self.scale_factor).normalized())
        
        elif self.stroke_img_item is not None:
            if self.stroke_img_item.is_painting:
                pos = self.inpaintLayer.mapFromScene(event.scenePos())
                if self.erase_img_key is None:
                    # painting
                    self.stroke_img_item.lineTo(pos)
                else:
                    rect = self.stroke_img_item.lineTo(pos, update=False)
                    if rect is not None:
                        self.drawingLayer.update(rect)

        elif self.clone_stamp_item is not None and self.clone_stamp_item.is_painting:
            pos = self.inpaintLayer.mapFromScene(event.scenePos())
            self.clone_stamp_item.lineTo(pos)
            # Move the source indicator to follow the brush offset
            if self.clone_source is not None and self.clone_stamp_item._stroke_origin is not None:
                src_local = self.inpaintLayer.mapFromScene(self.clone_source)
                offset = pos - self.clone_stamp_item._stroke_origin
                cur_src_local = src_local + offset
                cur_src_scene = self.inpaintLayer.mapToScene(cur_src_local)
                self._clone_last_src_scene = cur_src_scene
                self._showCloneSourceIndicator(cur_src_scene)
        
        elif (self.image_edit_mode == ImageEditMode.StampTool
              and self.clone_source is not None
              and self.clone_stamp_item is None):
            # Show clone source preview at cursor position
            self._updateClonePreview(event.scenePos())

        elif self.scale_tool_mode:
            self.scale_tool.emit(event.scenePos())
        
        elif self.rubber_band.isVisible() and self.rubber_band_origin is not None:
            self.rubber_band.setGeometry(QRectF(self.rubber_band_origin, event.scenePos()).normalized())
            sel_path = QPainterPath(self.rubber_band_origin)
            sel_path.addRect(self.rubber_band.geometry())
            if C.FLAG_QT6:
                self.setSelectionArea(sel_path, deviceTransform=self.gv.viewportTransform())
            else:
                self.setSelectionArea(sel_path, Qt.ItemSelectionMode.IntersectsItemBoundingRect, self.gv.viewportTransform())

        elif self.shift_line_preview is not None:
            self._update_line_preview(event.scenePos())

        return super().mouseMoveEvent(event)
    
    @property
    def scale_tool_mode(self):
        return self.drawMode() and self.gv.isVisible() and QApplication.keyboardModifiers() == Qt.KeyboardModifier.AltModifier

    def clearToolStates(self):
        self.end_scale_tool.emit()

    def selected_text_items(self, sort: bool = True) -> List[TextBlkItem]:
        sel_textitems = []
        selitems = self.selectedItems()
        for sel in selitems:
            if isinstance(sel, TextBlkItem):
                sel_textitems.append(sel)
        if sort:
            sel_textitems.sort(key = lambda x : x.idx)
        return sel_textitems

    def handle_ctrlv(self) -> bool:
        if not self.textEditMode():
            return False        
        if self.editing_textblkitem is not None and self.editing_textblkitem.isEditing():
            return False
        self.on_paste()
        return True

    def handle_ctrlc(self):
        if not self.textEditMode():
            return False        
        if self.editing_textblkitem is not None and self.editing_textblkitem.isEditing():
            return False
        self.on_copy()
        return True

    def scene_cursor_pos(self):
        origin = self.gv.mapFromGlobal(QCursor.pos())
        return self.gv.mapToScene(origin)

    # ---- Clone Stamp Helpers ----

    def setCloneSource(self, pos: QPointF):
        """Set the clone source point (in scene coordinates)."""
        self.clone_source = pos
        self._showCloneSourceIndicator(pos)
        self._buildClonePreviewPixmap()

    def _showCloneSourceIndicator(self, pos: QPointF):
        """Show a dashed circle + crosshair at the source position."""
        self._hideCloneSourceIndicator()
        pen = QPen(QColor(0, 255, 0, 200), 2, Qt.PenStyle.DashLine)
        pen.setDashPattern([4, 4])
        r = 12
        self.clone_source_item = QGraphicsEllipseItem(pos.x() - r, pos.y() - r, r * 2, r * 2)
        self.clone_source_item.setPen(pen)
        self.clone_source_item.setZValue(1000)
        self.addItem(self.clone_source_item)

        # Crosshair lines
        cross_len = 8
        cross_pen = QPen(QColor(0, 255, 0, 200), 1.5)
        h_line = QGraphicsLineItem(pos.x() - cross_len, pos.y(), pos.x() + cross_len, pos.y())
        v_line = QGraphicsLineItem(pos.x(), pos.y() - cross_len, pos.x(), pos.y() + cross_len)
        h_line.setPen(cross_pen)
        v_line.setPen(cross_pen)
        h_line.setZValue(1000)
        v_line.setZValue(1000)
        h_line.setParentItem(self.clone_source_item)
        v_line.setParentItem(self.clone_source_item)

    def _hideCloneSourceIndicator(self):
        if self.clone_source_item is not None:
            if self.clone_source_item.scene() == self:
                self.removeItem(self.clone_source_item)
            self.clone_source_item = None

    def startCloneStampStroke(self, pos: QPointF):
        """Begin a clone stamp stroke at pos (image-local coords)."""
        if self.clone_source is None:
            return
        self._hideClonePreview()
        # Snapshot current inpainted_array as the clone source image
        src_pixmap = ndarray2pixmap(self.imgtrans_proj.inpainted_array)
        src_qimg = src_pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        source_local = self.inpaintLayer.mapFromScene(self.clone_source)
        pen = QPen(Qt.GlobalColor.transparent, self.painting_pen.widthF())
        self.clone_stamp_item = CloneStampItem(
            src_qimg, source_local, pen, pos,
            self.img_window_size(), shape=self.painting_shape
        )
        self.clone_stamp_item.setParentItem(self.baseLayer)
        self.clone_stamp_item.setZValue(50)

    def finishCloneStampStroke(self):
        if self.clone_stamp_item is not None:
            # Update source point to last tracked position (follow offset)
            if self._clone_last_src_scene is not None:
                self.clone_source = self._clone_last_src_scene
                self._clone_last_src_scene = None
                self._buildClonePreviewPixmap()
            self.finish_painting.emit(self.clone_stamp_item)
            self.clone_stamp_item = None

    def rebuildClonePreview(self):
        """Rebuild the preview pixmap (e.g. after brush size change)."""
        self._clone_preview_pixmap = None
        self._buildClonePreviewPixmap()

    # ---- Clone Preview Helpers ----

    def _buildClonePreviewPixmap(self):
        """Extract brush-shaped patch from source, cache as semi-transparent pixmap."""
        self._clone_preview_pixmap = None
        if self.clone_source is None or not self.imgtrans_proj.inpainted_valid:
            return
        size = self.painting_pen.widthF()
        if size < 2:
            size = 2
        r = size / 2.0
        src_local = self.inpaintLayer.mapFromScene(self.clone_source)
        sx, sy = int(src_local.x() - r), int(src_local.y() - r)
        sw, sh = int(size), int(size)

        # Clamp to image bounds
        img_h, img_w = self.imgtrans_proj.inpainted_array.shape[:2]
        sx = max(0, min(sx, img_w - 2))
        sy = max(0, min(sy, img_h - 2))
        sw = min(sw, img_w - sx)
        sh = min(sh, img_h - sy)
        if sw < 1 or sh < 1:
            return

        patch = self.imgtrans_proj.inpainted_array[sy:sy+sh, sx:sx+sw]
        base_pm = ndarray2pixmap(patch)

        # Apply shape mask (circle → clip to ellipse)
        if self.painting_shape == 0:  # Circle
            masked = QPixmap(base_pm.size())
            masked.fill(Qt.GlobalColor.transparent)
            p = QPainter(masked)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            path = QPainterPath()
            path.addEllipse(0, 0, base_pm.width(), base_pm.height())
            p.setClipPath(path)
            p.drawPixmap(0, 0, base_pm)
            p.end()
            self._clone_preview_pixmap = masked
        else:
            self._clone_preview_pixmap = QPixmap(base_pm)

    def _updateClonePreview(self, scene_pos: QPointF):
        """Position the semi-transparent source preview at cursor, scaled with zoom."""
        if self._clone_preview_pixmap is None:
            return
        if self.clone_preview_item is None:
            self.clone_preview_item = QGraphicsPixmapItem()
            self.clone_preview_item.setOpacity(0.45)
            self.clone_preview_item.setZValue(999)
            self.clone_preview_item.setParentItem(self.baseLayer)
        self.clone_preview_item.setPixmap(self._clone_preview_pixmap)

        half = self._clone_preview_pixmap.width() / 2.0
        local_pos = self.baseLayer.mapFromScene(scene_pos)
        self.clone_preview_item.setPos(local_pos.x() - half, local_pos.y() - half)

    def _hideClonePreview(self):
        if self.clone_preview_item is not None:
            if self.clone_preview_item.scene() == self:
                self.removeItem(self.clone_preview_item)
            self.clone_preview_item = None

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        btn = event.button()
        if btn == Qt.MouseButton.MiddleButton:
            self.mid_btn_pressed = True
            self.pan_initial_pos = event.screenPos()
            return
        
        if self.imgtrans_proj.img_valid:
            if self.textblock_mode and len(self.selectedItems()) == 0 and self.textEditMode():
                if btn == Qt.MouseButton.RightButton:
                    return self.startCreateTextblock(event.scenePos())
            elif self.creating_normal_rect:
                if btn == Qt.MouseButton.RightButton or btn == Qt.MouseButton.LeftButton:
                    return self.startCreateTextblock(event.scenePos(), hide_control=True)

            elif btn == Qt.MouseButton.LeftButton:
                # user is drawing using the pen/inpainting tool
                if self.scale_tool_mode:
                    self.begin_scale_tool.emit(event.scenePos())
                elif self.image_edit_mode == ImageEditMode.StampTool and self.gv.ctrl_pressed:
                    # Ctrl+Click in StampTool mode → set clone source
                    self.setCloneSource(event.scenePos())
                elif self.painting:
                    shift_pressed = (event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
                    current_pos = self.inpaintLayer.mapFromScene(event.scenePos())

                    if self.image_edit_mode == ImageEditMode.StampTool:
                        # Clone stamp: use CloneStampItem instead of StrokeImgItem
                        self.startCloneStampStroke(current_pos)
                    elif shift_pressed:
                        self.shift_line_start = event.scenePos()
                        self._create_line_preview(event.scenePos())
                        return
                    else:
                        self._remove_line_preview()
                        self.addStrokeImageItem(current_pos, self.painting_pen)

            elif btn == Qt.MouseButton.RightButton:
                # user is drawing using eraser
                if self.painting and self.image_edit_mode != ImageEditMode.StampTool:
                    erasing = self.image_edit_mode == ImageEditMode.PenTool
                    self.addStrokeImageItem(self.inpaintLayer.mapFromScene(event.scenePos()), self.erasing_pen, erasing)
                else:   # rubber band selection
                    self.rubber_band_origin = event.scenePos()
                    self.rubber_band.setGeometry(QRectF(self.rubber_band_origin, self.rubber_band_origin).normalized())
                    self.rubber_band.show()
                    self.rubber_band.setZValue(1)

        return super().mousePressEvent(event)

    @property
    def creating_normal_rect(self):
        return self.image_edit_mode == ImageEditMode.RectTool and self.editor_index == 0

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        btn = event.button()

        self.hide_rubber_band()

        Qt.MouseButton.LeftButton
        if btn == Qt.MouseButton.MiddleButton:
            self.mid_btn_pressed = False
        textblk_created = False
        if self.creating_textblock:
            tgt = 0 if btn == Qt.MouseButton.LeftButton else 1
            textblk_created = self.endCreateTextblock(btn=tgt)
        if btn == Qt.MouseButton.RightButton:
            if self.stroke_img_item is not None:
                self.finish_erasing.emit(self.stroke_img_item)
            if self.textEditMode() and not textblk_created:
                self.context_menu_requested.emit(event.screenPos(), False)
        if btn == Qt.MouseButton.LeftButton:
            if self.shift_line_start is not None:
                # Shift+拖拽画直线：完成直线
                self.drawLineBetweenPoints(self.shift_line_start, event.scenePos())
                self._remove_line_preview()
                self.shift_line_start = None
            elif self.stroke_img_item is not None:
                self.finish_painting.emit(self.stroke_img_item)
            elif self.clone_stamp_item is not None:
                self.finishCloneStampStroke()
            elif self.scale_tool_mode:
                self.end_scale_tool.emit()
        return super().mouseReleaseEvent(event)

    def updateCanvas(self):
        self.editing_textblkitem = None
        self.stroke_img_item = None
        self.erase_img_key = None
        self.clone_source = None
        self._clone_preview_pixmap = None
        self.clone_stamp_item = None
        self._hideCloneSourceIndicator()
        self._hideClonePreview()
        self.txtblkShapeControl.setBlkItem(None)
        self.mid_btn_pressed = False
        self.search_widget.reInitialize()

        self.clearSelection()
        self.setProjSaveState(False)
        self.updateLayers()

        if self.base_pixmap is not None:
            pixmap = self.base_pixmap.copy()
            pixmap.fill(Qt.GlobalColor.transparent)
            self.textLayer.setPixmap(pixmap)

            im_rect = pixmap.rect()
            self.baseLayer.setRect(QRectF(im_rect))
            if im_rect != self.sceneRect():
                # 动态边距：缩放比例越大，边距越大，允许视角移动到边界外
                margin = int(CANVAS_SCENE_MARGIN * max(self.scale_factor, 1.0))
                self.setSceneRect(-margin, -margin, im_rect.width() + margin * 2, im_rect.height() + margin * 2)
            self.scaleImage(1)

        self.setDrawingLayer()


    def setDrawingLayer(self, img: Union[QPixmap, np.ndarray] = None):
        
        self.drawingLayer.clearAllDrawings()

        if not self.imgtrans_proj.img_valid:
            return
        if img is None:
            drawing_map = self.inpaintLayer.pixmap().copy()
            drawing_map.fill(Qt.GlobalColor.transparent)
        elif not isinstance(img, QPixmap):
            drawing_map = ndarray2pixmap(img)
        else:
            drawing_map = img
        self.drawingLayer.setPixmap(drawing_map)

    def setPaintMode(self, painting: bool):
        if painting:
            self.editing_textblkitem = None
            self.textblock_mode = False
        else:
            # self.gv.setCursor(self.default_cursor)
            self.gv.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.image_edit_mode = ImageEditMode.NONE

    @property
    def painting(self):
        return (self.image_edit_mode == ImageEditMode.PenTool
                or self.image_edit_mode == ImageEditMode.InpaintTool
                or self.image_edit_mode == ImageEditMode.StampTool)

    def setMaskTransparencyBySlider(self, slider_value: int):
        self.setMaskTransparency(slider_value / 100)

    def setOriginalTransparencyBySlider(self, slider_value: int):
        self.setOriginalTransparency(slider_value / 100)

    def setTextLayerTransparencyBySlider(self, slider_value: int):
        self.setTextLayerTransparency(slider_value / 100)

    def setTextBlockMode(self, mode: bool):
        self.textblock_mode = mode

    def on_create_contextmenu(self, pos: QPoint, is_textpanel: bool):
        if self.textEditMode() and not self.creating_textblock:
            menu = QMenu(self.gv)
            copy_act = menu.addAction(self.tr("Copy"))
            copy_act.setShortcut(QKeySequence.StandardKey.Copy)
            paste_act = menu.addAction(self.tr("Paste"))
            paste_act.setShortcut(QKeySequence.StandardKey.Paste)
            delete_act = menu.addAction(self.tr("Delete"))
            delete_act.setShortcut(QKeySequence("Ctrl+D"))
            copy_src_act = menu.addAction(self.tr("Copy source text"))
            copy_src_act.setShortcut(QKeySequence("Ctrl+Shift+C"))
            paste_src_act = menu.addAction(self.tr("Paste source text"))
            paste_src_act.setShortcut(QKeySequence("Ctrl+Shift+V"))
            delete_recover_act = menu.addAction(self.tr("Delete and Recover removed text"))
            delete_recover_act.setShortcut(QKeySequence("Ctrl+Shift+D"))

            menu.addSeparator()

            format_act = menu.addAction(self.tr("Apply font formatting"))
            layout_act = menu.addAction(self.tr("Auto layout"))
            angle_act = menu.addAction(self.tr("Reset Angle"))
            squeeze_act = menu.addAction(self.tr("Squeeze"))
            menu.addSeparator()
            translate_act = menu.addAction(self.tr("translate"))
            ocr_act = menu.addAction(self.tr("OCR"))
            ocr_translate_act = menu.addAction(self.tr("OCR and translate"))
            ocr_translate_inpaint_act = menu.addAction(self.tr("OCR, translate and inpaint"))
            inpaint_act = menu.addAction(self.tr("inpaint"))

            rst = menu.exec(pos)
            
            if rst == delete_act:
                self.delete_textblks.emit(0)
            elif rst == delete_recover_act:
                self.delete_textblks.emit(1)
            elif rst == copy_act:
                self.on_copy()
            elif rst == paste_act:
                self.on_paste()
            elif rst == copy_src_act:
                self.copy_src_signal.emit()
            elif rst == paste_src_act:
                self.paste_src_signal.emit()
            elif rst == format_act:
                self.format_textblks.emit()
            elif rst == layout_act:
                self.layout_textblks.emit()
            elif rst == angle_act:
                self.reset_angle.emit()
            elif rst == squeeze_act:
                self.squeeze_blk.emit()
            elif rst == translate_act:
                self.run_blktrans.emit(-1)
            elif rst == ocr_act:
                self.run_blktrans.emit(0)
            elif rst == ocr_translate_act:
                self.run_blktrans.emit(1)
            elif rst == ocr_translate_inpaint_act:
                self.run_blktrans.emit(2)
            elif rst == inpaint_act:
                self.run_blktrans.emit(3)

    @property
    def have_selected_blkitem(self):
        return len(self.selected_text_items()) > 0

    def on_paste(self, p: QPointF = None):
        if self.textEditMode():
            if p is None:
                p = self.scene_cursor_pos()
            if self.have_selected_blkitem:
                self.paste2selected_textitems.emit()
            else:
                self.paste_textblks.emit(p)

    def on_copy(self):
        if self.textEditMode():
            if self.have_selected_blkitem:
                self.copy_textblks.emit()

    def hide_rubber_band(self):
        if self.rubber_band.isVisible():
            self.rubber_band.hide()
            self.rubber_band_origin = None
    
    def on_hide_canvas(self):
        self.clear_states()

    def on_activation_changed(self):
        self.clear_states()
        for textitem in self.selected_text_items():
            if textitem.isEditing():
                self.editing_textblkitem = textitem

    def clear_states(self):
        self.creating_textblock = False
        self.create_block_origin = None
        self.editing_textblkitem = None
        self.gv.ctrl_pressed = False
        self.clone_source = None
        self._clone_preview_pixmap = None
        self._hideCloneSourceIndicator()
        self._hideClonePreview()
        if self.stroke_img_item is not None:
            self.removeItem(self.stroke_img_item)
        if self.clone_stamp_item is not None:
            self.finishCloneStampStroke()

    def setProjSaveState(self, un_saved: bool):
        if un_saved == self.projstate_unsaved:
            return
        else:
            self.projstate_unsaved = un_saved
            self.proj_savestate_changed.emit(un_saved)

    def removeItem(self, item: QGraphicsItem) -> None:
        self.block_selection_signal = True
        super().removeItem(item)
        if isinstance(item, StrokeImgItem):
            item.setParentItem(None)
            self.stroke_img_item = None
            self.erase_img_key = None
        elif isinstance(item, CloneStampItem):
            item.setParentItem(None)
            self.clone_stamp_item = None
        self.block_selection_signal = False

    def get_active_undostack(self) -> QUndoStack:
        if self.textEditMode():
            return self.text_undo_stack
        elif self.drawMode():
            return self.draw_undo_stack
        return None

    def push_undo_command(self, command: QUndoCommand, update_pushed_step=True):
        if self.textEditMode():
            self.push_text_command(command, update_pushed_step)
        elif self.drawMode():
            self.push_draw_command(command, update_pushed_step)
        else:
            return

    def push_draw_command(self, command: QUndoCommand, update_pushed_step=True):
        if command is not None:
            self.draw_undo_stack.push(command)
        if update_pushed_step:
            self.num_pushed_drawstep += 1
            self.on_drawstack_changed()

    def push_text_command(self, command: QUndoCommand, update_pushed_step=True):
        if command is not None:
            self.text_undo_stack.push(command)
        if update_pushed_step:
            self.num_pushed_textstep += 1
            self.on_textstack_changed()

    def on_drawstack_changed(self):
        if self.num_pushed_drawstep != self.saved_drawundo_step:
            self.setProjSaveState(True)
        elif self.num_pushed_textstep == self.saved_textundo_step:
            self.setProjSaveState(False)

    def on_textstack_changed(self):
        if self.num_pushed_textstep != self.saved_textundo_step:
            self.setProjSaveState(True)
        elif self.num_pushed_drawstep == self.saved_drawundo_step:
            self.setProjSaveState(False)
        self.textstack_changed.emit()

    def redo_textedit(self):
        self.num_pushed_textstep += 1
        self.text_undo_stack.redo()

    def undo_textedit(self):
        if self.num_pushed_textstep > 0:
            self.num_pushed_textstep -= 1
        self.text_undo_stack.undo()

    def redo(self):
        if self.textEditMode():
            undo_stack = self.text_undo_stack
            self.num_pushed_textstep += 1
            self.on_textstack_changed()
        elif self.drawMode():
            undo_stack = self.draw_undo_stack
            self.num_pushed_drawstep += 1
            self.on_drawstack_changed()
        else:
            return
        if undo_stack is not None:
            undo_stack.redo()
            if undo_stack == self.text_undo_stack:
                self.txtblkShapeControl.updateBoundingRect()

    def undo(self):
        if self.textEditMode():
            undo_stack = self.text_undo_stack
            if self.num_pushed_textstep > 0:
                self.num_pushed_textstep -= 1
            self.on_textstack_changed()
        elif self.drawMode():
            undo_stack = self.draw_undo_stack
            if self.num_pushed_drawstep > 0:
                self.num_pushed_drawstep -= 1
            self.on_drawstack_changed()
        else:
            return
        if undo_stack is not None:
            undo_stack.undo()
            if undo_stack == self.text_undo_stack:
                self.txtblkShapeControl.updateBoundingRect()

    def clear_undostack(self, update_saved_step=False):
        if update_saved_step:
            self.saved_drawundo_step = 0
            self.saved_textundo_step = 0
            self.num_pushed_textstep = 0
            self.num_pushed_drawstep = 0
        self.draw_undo_stack.clear()
        self.text_undo_stack.clear()

    def clear_text_stack(self):
        self.num_pushed_textstep = 0
        self.text_undo_stack.clear()

    def clear_draw_stack(self):
        self.num_pushed_drawstep = 0
        self.draw_undo_stack.clear()

    def update_saved_undostep(self):
        self.saved_drawundo_step = self.num_pushed_drawstep
        self.saved_textundo_step = self.num_pushed_textstep

    def text_change_unsaved(self) -> bool:
        return self.saved_textundo_step != self.num_pushed_textstep

    def draw_change_unsaved(self) -> bool:
        return self.saved_drawundo_step != self.num_pushed_drawstep

    def prepareClose(self):
        self.blockSignals(True)
        self.text_undo_stack.blockSignals(True)
        self.draw_undo_stack.blockSignals(True)

