import math
from functools import cached_property

import numpy as np
from qtpy.QtWidgets import QGraphicsPixmapItem, QGraphicsItem, QWidget, QGraphicsSceneHoverEvent, QLabel, QStyleOptionGraphicsItem, QGraphicsSceneMouseEvent, QGraphicsRectItem
from qtpy.QtCore import Qt, QRect, QRectF, QPointF, QPoint
from qtpy.QtGui import QPainter, QPen, QColor

from utils.imgproc_utils import xywh2xyxypoly, rotate_polygons
from .cursor import rotateCursorList, resizeCursorList
from .textitem import TextBlkItem

CBEDGE_WIDTH = 30

VISUALIZE_HITBOX = False
ctrlidx_to_hitbox = {
    0: [-0.75, -0.75, 0.75, 0.75],
    1: [-0.5, -0.75, 1, 0.75],
    2: [0., -0.75, 0.75, 0.75],
    3: [0., -0.5, 0.75, 1],
    4: [0., 0., 0.75, 0.75],
    5: [-0.5, 0., 1, 0.75],
    6: [-0.75, 0., 0.75, 0.75],
    7: [-0.75, -0.5, 0.75, 1]
}
for k, v in ctrlidx_to_hitbox.items():
    ctrlidx_to_hitbox[k] = np.array(v, dtype=np.float32)

ctrlidx_to_visiblebox = {
    0: [0.25, 0.25, 0.75, 0.75],
    1: [0.25, 0.25, 0.75],
    2: [0., 0.25, 0.75, 0.75],
    3: [0., 0.25, 0.75, 1],
    4: [0., 0., 0.75, 0.75],
    5: [0.25, 0., 1, 0.75],
    6: [0.25, 0., 0.75, 0.75],
    7: [0.25, 0.25, 0.75, 1]
}
for k, v in ctrlidx_to_visiblebox.items():
    ctrlidx_to_visiblebox[k] = np.array(v, dtype=np.float32)

class ControlBlockItem(QGraphicsRectItem):
    DRAG_NONE = 0
    DRAG_RESHAPE = 1
    DRAG_ROTATE = 2
    DRAG_PATH = 3  # Alt+drag → path deformation
    CURSOR_IDX = -1
    def __init__(self, parent, idx: int):
        super().__init__(parent)
        self.idx = idx
        self.ctrl: TextBlkShapeControl = parent
        self.edge_width = 0
        self.drag_mode = self.DRAG_NONE
        self.setAcceptHoverEvents(True)
        self.setFlags(QGraphicsItem.GraphicsItemFlag.ItemIsMovable | QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.updateEdgeWidth(CBEDGE_WIDTH)

    def updateEdgeWidth(self, edge_width: float):
        self.edge_width = edge_width
        self.visible_len = self.edge_width / 2
        self.block_shift_value = self.edge_width * 0.75
        self.pen_width = edge_width / CBEDGE_WIDTH * 2 
        offset = self.edge_width * ctrlidx_to_visiblebox[self.idx]
        self.visible_rect = QRectF(offset[0], offset[1], self.visible_len, self.visible_len)
        hitbox = ctrlidx_to_hitbox[self.idx]
        w = hitbox[2] * self.edge_width
        h = hitbox[3] * self.edge_width
        self.setRect(0, 0, w, h)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget) -> None:
        rect = QRectF(self.visible_rect)
        rect.setTopLeft(self.boundingRect().topLeft()+rect.topLeft())
        painter.setPen(QPen(QColor(75, 75, 75), self.pen_width, Qt.PenStyle.SolidLine, Qt.SquareCap))
        painter.fillRect(rect, QColor(200, 200, 200, 125))
        painter.drawRect(rect)
        if VISUALIZE_HITBOX:
            painter.setPen(QPen(QColor(75, 125, 0), self.pen_width, Qt.PenStyle.SolidLine, Qt.SquareCap))
            painter.drawRect(self.boundingRect())

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent) -> None:        
        return super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        self.drag_mode = self.DRAG_NONE
        self.CURSOR_IDX = -1
        return super().hoverLeaveEvent(event)

    def hoverMoveEvent(self, event: QGraphicsSceneHoverEvent) -> None:
        # Alt + drag path deformation disabled.
        # alt_held = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        angle = self.ctrl.rotation() + 45 * self.idx
        idx = self.get_angle_idx(angle)

        # if alt_held and self.ctrl.blk_item is not None \
        #         and not self.ctrl.blk_item.fontformat.vertical:
        #     # Alt held → path deformation mode, override cursor
        #     self.setCursor(Qt.CursorShape.SizeVerCursor)
        #     self.drag_mode = self.DRAG_PATH
        if self.visible_rect.contains(event.pos()):
            self.setCursor(resizeCursorList[idx % 4])
        else:
            self.setCursor(rotateCursorList[idx])
        self.CURSOR_IDX = idx
        return super().hoverMoveEvent(event)

    def hoverLeaveEvent(self, event: 'QGraphicsSceneHoverEvent') -> None:
        if self.drag_mode == self.DRAG_NONE:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        return super().hoverLeaveEvent(event)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        self.ctrl.ctrlblockPressed()
        if event.button() == Qt.MouseButton.LeftButton and self.ctrl.blk_item is not None:
            blk_item = self.ctrl.blk_item
            blk_item.setSelected(True)

            # Alt + drag path deformation disabled.
            # alt_held = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
            # if alt_held and not blk_item.fontformat.vertical:
            #     self.drag_mode = self.DRAG_PATH
            #     self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
            #     ff = blk_item.fontformat
            #     pd = ff.path_data if ff.path_data else [0.0]
            #     cur = pd[0] if pd else 0.0
            #     if ff.path_type == 2:
            #         cur = -cur
            #     self._path_start_y = event.scenePos().y()
            #     self._path_start_curvature = cur
            if self.visible_rect.contains(event.pos()):
                self.ctrl.reshaping = True
                self.drag_mode = self.DRAG_RESHAPE
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
                blk_item.startReshape()
            else:
                self.drag_mode = self.DRAG_ROTATE
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
                preview = self.ctrl.previewPixmap

                preview.setPixmap(blk_item.toPixmap().copy(blk_item.unpadRect(blk_item.boundingRect()).toRect()))
                preview.setOpacity(0.7)
                preview.setVisible(True)
                rotate_vec = event.scenePos() - self.ctrl.sceneBoundingRect().center()
                self.updateAngleLabelPos()
                rotation = np.rad2deg(math.atan2(rotate_vec.y(), rotate_vec.x()))
                self.rotate_start = - rotation + self.ctrl.rotation()
        event.accept()

    def updateAngleLabelPos(self):
        angleLabel = self.ctrl.angleLabel
        sp = self.scenePos()
        gv = angleLabel.parent()
        pos = gv.mapFromScene(sp)
        x = max(min(pos.x(), gv.width() - angleLabel.width()), 0)
        y = max(min(pos.y(), gv.height() - angleLabel.height()), 0)
        angleLabel.move(QPoint(x, y))
        angleLabel.setText("{:.1f}°".format(self.ctrl.rotation()))
        if not angleLabel.isVisible():
            angleLabel.setVisible(True)
            angleLabel.raise_()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        super().mouseMoveEvent(event)
        blk_item = self.ctrl.blk_item
        if blk_item is None:
            return
        # Alt + drag path deformation disabled.
        # if self.drag_mode == self.DRAG_PATH:
        #     dy = self._path_start_y - event.scenePos().y()  # up = positive curvature
        #     sensitivity = 0.005  # curvature per pixel
        #     cur = self._path_start_curvature + dy * sensitivity
        #     cur = max(-1.0, min(1.0, cur))
        #     if abs(cur) < 0.005:
        #         blk_item.setPathMode(0, [0.0])  # turn off
        #     elif cur > 0:
        #         blk_item.setPathMode(1, [cur])   # arc above
        #     else:
        #         blk_item.setPathMode(2, [-cur])  # arc below
        if self.drag_mode == self.DRAG_RESHAPE:    
            block_group = self.ctrl.ctrlblock_group
            crect = self.ctrl.rect()
            pos_x, pos_y = 0, 0
            opposite_block = block_group[(self.idx + 4) % 8 ]
            oppo_pos = opposite_block.pos()
            if self.idx % 2 == 0:
                if self.idx == 0:
                    pos_x = min(self.pos().x(), oppo_pos.x())
                    pos_y = min(self.pos().y(), oppo_pos.y())
                    crect.setX(pos_x + self.block_shift_value)
                    crect.setY(pos_y + self.block_shift_value)
                elif self.idx == 2:
                    pos_x = max(self.pos().x(), oppo_pos.x())
                    pos_y = min(self.pos().y(), oppo_pos.y())
                    crect.setWidth(pos_x - oppo_pos.x() - self.block_shift_value)
                    crect.setY(pos_y+self.block_shift_value)
                elif self.idx == 4:
                    pos_x = max(self.pos().x(), oppo_pos.x())
                    pos_y = max(self.pos().y(), oppo_pos.y())
                    crect.setWidth(pos_x-oppo_pos.x() - self.block_shift_value)
                    crect.setHeight(pos_y-oppo_pos.y() - self.block_shift_value)
                else:   # idx == 6
                    pos_x = min(self.pos().x(), oppo_pos.x())
                    pos_y = max(self.pos().y(), oppo_pos.y())
                    crect.setX(pos_x+self.block_shift_value)
                    crect.setHeight(pos_y-oppo_pos.y() - self.block_shift_value)
            else:
                if self.idx == 1:
                    pos_y = min(self.pos().y(), oppo_pos.y())
                    crect.setY(pos_y+self.block_shift_value)
                elif self.idx == 3:
                    pos_x = max(self.pos().x(), oppo_pos.x())
                    crect.setWidth(pos_x-oppo_pos.x() - self.block_shift_value)
                elif self.idx == 5:
                    pos_y = max(self.pos().y(), oppo_pos.y())
                    crect.setHeight(pos_y-oppo_pos.y() - self.block_shift_value)
                else:   # idx == 7
                    pos_x = min(self.pos().x(), oppo_pos.x())
                    crect.setX(pos_x+self.block_shift_value)
            
            self.ctrl.setRect(crect)
            scale = self.ctrl.current_scale
            new_center = self.ctrl.sceneBoundingRect().center()
            new_xy = QPointF(new_center.x() / scale - crect.width() / 2, new_center.y() / scale - crect.height() / 2)
            rect = QRectF(new_xy.x(), new_xy.y(), crect.width(), crect.height())
            blk_item.setRect(rect)

        elif self.drag_mode == self.DRAG_ROTATE:   # rotating
            rotate_vec = event.scenePos() - self.ctrl.sceneBoundingRect().center()
            rotation = np.rad2deg(math.atan2(rotate_vec.y(), rotate_vec.x()))
            self.ctrl.setAngle((rotation+self.rotate_start))
            # angle = self.ctrl.rotation()
            angle = self.ctrl.rotation() + 45 * self.idx
            idx = self.get_angle_idx(angle)
            if self.CURSOR_IDX != idx:
                self.setCursor(rotateCursorList[idx])
                self.CURSOR_IDX = idx
            self.updateAngleLabelPos()

    def get_angle_idx(self, angle) -> int:
        idx = int((angle + 22.5) % 360 / 45)
        return idx
    
    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.ctrl.reshaping = False
            if self.drag_mode == self.DRAG_RESHAPE:
                self.ctrl.blk_item.endReshape()
            elif self.drag_mode == self.DRAG_ROTATE:
                self.ctrl.blk_item.rotated.emit(self.ctrl.rotation())
            # Alt + drag path deformation disabled.
            # elif self.drag_mode == self.DRAG_PATH:
            #     self.ctrl.blk_item.push_undo_stack.emit(1, False)
            #     self.ctrl._updateCurvatureHandle()
            self.drag_mode = self.DRAG_NONE
            
            self.ctrl.previewPixmap.setVisible(False)
            self.ctrl.angleLabel.setVisible(False)
            self.ctrl.blk_item.update()
            self.ctrl.updateBoundingRect()
            return super().mouseReleaseEvent(event)

class CurvatureHandle(QGraphicsRectItem):
    """Small draggable handle at the center of path-enabled text blocks.

    Dragging vertically adjusts the arc curvature (path_data[0]).
    """
    HANDLE_SIZE = 12
    CURVATURE_STEP = 0.01  # per pixel dragged

    def __init__(self, parent: 'TextBlkShapeControl'):
        super().__init__(parent)
        self.ctrl = parent
        self._dragging = False
        self._drag_start_y = 0.0
        self._start_curvature = 0.3
        self.setRect(0, 0, self.HANDLE_SIZE, self.HANDLE_SIZE)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setZValue(10)
        self.hide()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget=None):
        painter.setPen(QPen(QColor(255, 140, 0), 2))
        painter.setBrush(QColor(255, 140, 0, 180))
        r = self.rect()
        painter.drawEllipse(r.center(), r.width() / 2 - 1, r.height() / 2 - 1)

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_y = event.scenePos().y()
            blk_item = self.ctrl.blk_item
            if blk_item is not None and blk_item.fontformat is not None:
                pd = blk_item.fontformat.path_data
                self._start_curvature = pd[0] if pd else 0.3
        event.accept()

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if not self._dragging:
            return
        dy = self._drag_start_y - event.scenePos().y()  # up = positive curvature
        new_curvature = self._start_curvature + dy * self.CURVATURE_STEP
        new_curvature = max(0.0, min(1.0, new_curvature))
        blk_item = self.ctrl.blk_item
        if blk_item is not None:
            blk_item.setPathMode(blk_item.fontformat.path_type, [new_curvature])
        event.accept()

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging:
            self._dragging = False
            blk_item = self.ctrl.blk_item
            if blk_item is not None:
                blk_item.push_undo_stack.emit(1, False)
        event.accept()

    def hoverEnterEvent(self, event: QGraphicsSceneHoverEvent):
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        return super().hoverEnterEvent(event)


class TextBlkShapeControl(QGraphicsRectItem):
    blk_item : TextBlkItem = None
    ctrl_block: ControlBlockItem = None
    reshaping: bool = False
    
    def __init__(self, parent) -> None:
        super().__init__()
        self.gv = parent
        self.ctrlblock_group = [
            ControlBlockItem(self, idx) for idx in range(8)
        ]

        self.previewPixmap = QGraphicsPixmapItem(self)
        self.previewPixmap.setVisible(False)
        pen = QPen(QColor(69, 71, 87), 2, Qt.PenStyle.SolidLine)
        pen.setDashPattern([7, 14])
        self.setPen(pen)
        self.setVisible(False)

        self.angleLabel = QLabel(parent)
        self.angleLabel.setText("{:.1f}°".format(self.rotation()))
        self.angleLabel.setObjectName("angleLabel")
        self.angleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.angleLabel.setHidden(True)

        self.curvature_handle = CurvatureHandle(self)

        self.current_scale = 1.
        self.need_rescale = False
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def setBlkItem(self, blk_item: TextBlkItem):
        if self.blk_item == blk_item and self.isVisible():
            return
        if self.blk_item is not None:
            self.blk_item.under_ctrl = False
            if self.blk_item.isEditing():
                self.blk_item.endEdit()
            self.blk_item.update()

        self.blk_item = blk_item
        if blk_item is None:
            self.hide()
            self.curvature_handle.hide()
            return
        blk_item.under_ctrl = True
        blk_item.update()
        self.updateBoundingRect()
        self.show()
        self._updateCurvatureHandle()

    def _updateCurvatureHandle(self):
        """Show/hide curvature handle based on blk_item's path_type."""
        if self.blk_item is None:
            self.curvature_handle.hide()
            return
        ff = self.blk_item.fontformat
        if ff is not None and ff.path_type > 0:
            # Position at the vertical center of the control
            br = self.rect()
            cx = br.center().x() - CurvatureHandle.HANDLE_SIZE / 2.0
            cy = br.center().y() - CurvatureHandle.HANDLE_SIZE / 2.0
            self.curvature_handle.setPos(cx, cy)
            self.curvature_handle.show()
        else:
            self.curvature_handle.hide()

    def updateBoundingRect(self):
        if self.blk_item is None:
            return
        abr = self.blk_item.absBoundingRect(qrect=True)
        br = QRectF(0, 0, abr.width(), abr.height())
        self.setRect(br)
        self.blk_item.setCenterTransform()
        self.setTransformOriginPoint(self.blk_item.transformOriginPoint())
        self.setPos(abr.x(), abr.y())
        self.setAngle(self.blk_item.angle)

    def setRect(self, *args): 
        super().setRect(*args)
        self.updateControlBlocks()

    def updateControlBlocks(self):
        b_rect = self.rect()
        b_rect = [b_rect.x(), b_rect.y(), b_rect.width(), b_rect.height()]
        corner_pnts = xywh2xyxypoly(np.array([b_rect])).reshape(-1, 2)
        edge_pnts = (corner_pnts[[1, 2, 3, 0]] + corner_pnts) / 2
        pnts = [edge_pnts, corner_pnts]
        for ii, ctrlblock in enumerate(self.ctrlblock_group):
            is_corner = not ii % 2
            idx = ii // 2
            hitbox_xy = ctrlidx_to_hitbox[ii][:2]
            pos = pnts[is_corner][idx] + hitbox_xy * ctrlblock.edge_width
            ctrlblock.setPos(pos[0], pos[1])

    def setAngle(self, angle: int) -> None:
        center = self.boundingRect().center()
        self.setTransformOriginPoint(center)
        self.setRotation(angle)

    def ctrlblockPressed(self):
        self.scene().clearSelection()
        if self.blk_item is not None:
            self.blk_item.endEdit()

    def paint(self, painter: QPainter, option: 'QStyleOptionGraphicsItem', widget = ...) -> None:
        painter.setCompositionMode(QPainter.CompositionMode.RasterOp_NotDestination)
        super().paint(painter, option, widget)

    def hideControls(self):
        for ctrl in self.ctrlblock_group:
            ctrl.hide()

    def showControls(self):
        for ctrl in self.ctrlblock_group:
            ctrl.show()

    def updateScale(self, scale: float):
        if not self.isVisible():
            if scale != self.current_scale:
                self.need_rescale = True
                self.current_scale = scale
            return

        self.current_scale = scale
        scale = 1 / scale
        pen = self.pen()
        pen.setWidthF(2 * scale)
        self.setPen(pen)
        for ctrl in self.ctrlblock_group:
            ctrl.updateEdgeWidth(CBEDGE_WIDTH * scale)

    def show(self) -> None:
        super().show()
        if self.need_rescale:
            self.updateScale(self.current_scale)
            self.need_rescale = False
        self.setZValue(1)

    def startEditing(self):
        self.setCursor(Qt.CursorShape.IBeamCursor)
        for ctrlb in self.ctrlblock_group:
            ctrlb.hide()
        self.curvature_handle.hide()

    def endEditing(self):
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        if self.isVisible():
            for ctrlb in self.ctrlblock_group:
                ctrlb.show()
            self._updateCurvatureHandle()