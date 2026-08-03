"""
Path-based Text Layout Engine for BallonsTranslator.
Supports arc/bezier text deformation by placing each character
independently along a QPainterPath with proper rotation.

Characters are rendered directly via QPainter.drawText() — QTextLine is
only used for a minimal "dummy" layout so Qt's selection / cursor machinery
has valid line geometries to query.
"""

import math
from typing import List

from qtpy.QtCore import Qt, QPointF, QRectF, QSizeF, Signal
from qtpy.QtGui import (
    QPainterPath, QTextOption, QPainter, QAbstractTextDocumentLayout,
    QFontMetricsF, QTextLine, QTextBlock, QTextFormat, QPen, QColor
)

from utils.fontformat import FontFormat, pt2px
from utils import shared as C
from .misc import pixmap2ndarray

# Reuse existing hit-test helpers from scene_textlayout
PUNSET_VERNEEDROTATE = set()
_is_vert_rotatable = None  # lazy import

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _build_qpainter_path(path_type: int, path_data: List[float],
                          available_w: float, available_h: float,
                          doc_margin: float) -> QPainterPath:
    """Build a QPainterPath from path_type and path_data.

    Coordinates are in layout space (origin = document margin offset).
    """
    path = QPainterPath()
    w = available_w
    h = available_h
    m = doc_margin

    if w <= 0 or h <= 0:
        # Degenerate rect — return a tiny flat path so nothing crashes
        path.moveTo(0, 0)
        path.lineTo(1, 0)
        return path

    curvature = path_data[0] if path_data else 0.3
    curvature = max(0.0, min(1.0, curvature))

    if path_type == 1:
        # Arc above (smile / concave up): baseline bows upward
        bow = curvature * h * 0.7
        path.moveTo(m, m + h)
        path.quadTo(m + w / 2.0, m - bow, m + w, m + h)
    elif path_type == 2:
        # Arc below (frown / concave down): baseline bows downward
        bow = curvature * h * 0.7
        path.moveTo(m, m)
        path.quadTo(m + w / 2.0, m + h + bow, m + w, m)
    elif path_type == 3:
        # Bezier: path_data = [cp1x, cp1y, cp2x, cp2y, end_x, end_y]
        # All relative to (margin, margin)
        if len(path_data) >= 6:
            cp1x = m + path_data[0]
            cp1y = m + path_data[1]
            cp2x = m + path_data[2]
            cp2y = m + path_data[3]
            end_x = m + path_data[4]
            end_y = m + path_data[5]
            path.moveTo(m, m + h)
            path.cubicTo(cp1x, cp1y, cp2x, cp2y, end_x, end_y)
        else:
            path.moveTo(m, m + h)
            path.lineTo(m + w, m + h)
    else:
        # Flat horizontal line at baseline
        path.moveTo(m, m + h)
        path.lineTo(m + w, m + h)

    return path


# ---------------------------------------------------------------------------
# Path layout engine
# ---------------------------------------------------------------------------

class PathTextDocumentLayout(QAbstractTextDocumentLayout):
    """Custom document layout that places characters along a QPainterPath.

    Only horizontal text is supported. Each character becomes a single-column
    QTextLine positioned on the path and rotated to the local tangent.

    Works alongside the existing SceneTextLayout hierarchy; does NOT inherit
    from it to avoid coupling to vertical-text internals.
    """

    size_enlarged = Signal()  # for TextBlkItem compatibility

    def __init__(self, doc, fontformat: FontFormat):
        super().__init__(doc)
        self.fontformat = fontformat
        self.max_width = 0
        self.max_height = 0
        self.available_width = 0
        self.available_height = 0
        self.relayout_on_changed = True

        # Compatibility attributes for TextBlkItem
        self._draw_offset = []
        self._is_painting_stroke = False

        # Per-block per-line angle/position storage
        self._char_angles: List[float] = []       # parallel to lines
        self._char_positions: List[QPointF] = []  # parallel to lines
        self._line_to_char_idx: List[int] = []     # character index for each line

        # Pre-computed bounds
        self._actual_bounds = QRectF()

    # ---- public API -------------------------------------------------------

    def setMaxSize(self, max_width: float, max_height: float, relayout=True):
        self.max_width = max_width
        self.max_height = max_height
        doc_margin = self.document().documentMargin() * 2
        self.available_width = max(max_width - doc_margin, 0)
        self.available_height = max(max_height - doc_margin, 0)
        if relayout:
            self.reLayout()

    def max_font_size(self, to_px=False) -> float:
        """Return the largest font size in the document."""
        fs = self.document().defaultFont().pointSizeF()
        if to_px:
            fs = pt2px(fs)
        return fs

    def documentSize(self) -> QSizeF:
        return QSizeF(self.max_width, self.max_height)

    def documentChanged(self, position: int, charsRemoved: int, charsAdded: int):
        if not self.relayout_on_changed:
            return
        self.reLayout()

    # ---- layout -----------------------------------------------------------

    def reLayout(self):
        """Full relayout: clear then layout all blocks."""
        doc = self.document()
        self._char_angles.clear()
        self._char_positions.clear()
        self._line_to_char_idx.clear()

        block = doc.firstBlock()
        while block.isValid():
            self.layoutBlock(block)
            block = block.next()

        self._compute_bounds()
        self.documentSizeChanged.emit(QSizeF(self.max_width, self.max_height))

    def layoutBlock(self, block: QTextBlock):
        """Compute per-character positions and angles along the path.

        Does NOT rely on QTextLayout.createLine() for character-level splitting
        (that API is unreliable for single-char lines across Qt versions).
        Instead we compute positions directly from QPainterPath and store them
        in parallel arrays; draw() uses QPainter.drawText() directly.
        """
        doc = self.document()
        doc_margin = doc.documentMargin()

        blk_text = block.text()
        blk_text_len = len(blk_text)
        if blk_text_len == 0:
            return

        # ---- set up a minimal QTextLayout so Qt's cursor / selection machinery
        #      still sees valid line geometries --------------------------------
        block.clearLayout()
        tl = block.layout()
        option = doc.defaultTextOption()
        option.setWrapMode(QTextOption.WrapAnywhere)
        tl.setTextOption(option)
        tl.beginLayout()
        dummy_line = tl.createLine()
        if dummy_line.isValid():
            dummy_line.setPosition(QPointF(0, 0))
        tl.endLayout()
        # --------------------------------------------------------------------

        # ---- compute per-character path positions ---------------------------
        char_fmt = block.charFormat()
        font = char_fmt.font()
        fm = QFontMetricsF(font)
        letter_spacing = self.fontformat.letter_spacing

        path_type = self.fontformat.path_type
        path_data = self.fontformat.path_data if self.fontformat.path_data else [0.3]
        path = _build_qpainter_path(
            path_type, path_data,
            self.available_width, self.available_height, doc_margin
        )
        path_len = path.length()
        if path_len <= 0:
            return

        # Compute each character's advance along the path
        char_advances = []
        total_advance = 0.0
        for ch in blk_text:
            if ch == '\n':
                continue
            adv = fm.horizontalAdvance(ch)
            if adv <= 0:
                adv = fm.averageCharWidth()
            adv *= letter_spacing
            char_advances.append(adv)
            total_advance += adv

        if total_advance <= 0:
            return

        # Place each character on the path
        cumulative = 0.0
        char_idx = 0
        adv_idx = 0
        angles = []
        positions = []
        char_indexes = []

        for _i, ch in enumerate(blk_text):
            if ch == '\n':
                continue

            adv = char_advances[adv_idx]
            adv_idx += 1
            mid_t = (cumulative + adv / 2.0) / total_advance
            mid_t = max(0.0, min(1.0, mid_t))

            point = path.pointAtPercent(mid_t)
            angle = path.angleAtPercent(mid_t)

            angles.append(angle)
            positions.append(point)
            char_indexes.append(char_idx)

            cumulative += adv
            char_idx += 1

        self._char_angles.extend(angles)
        self._char_positions.extend(positions)
        self._line_to_char_idx.extend(char_indexes)
        # --------------------------------------------------------------------

    def _compute_bounds(self):
        """Compute the actual bounding rect of all placed characters."""
        if not self._char_positions:
            self._actual_bounds = QRectF(0, 0,
                                          max(self.max_width, 1),
                                          max(self.max_height, 1))
            return

        doc_margin = self.document().documentMargin()
        max_font_h = 0.0
        for line_no in range(len(self._char_positions)):
            # Rough estimate: font height ~ largest char in document
            pass  # will refine later

        # Expand bounds to include angled characters
        # For now, use generous padding
        padding = self.available_height * 0.4  # generous
        min_x = 0.0
        min_y = 0.0
        max_x = self.max_width
        max_y = self.max_height

        for pt in self._char_positions:
            min_x = min(min_x, pt.x() - padding)
            min_y = min(min_y, pt.y() - padding)
            max_x = max(max_x, pt.x() + padding)
            max_y = max(max_y, pt.y() + padding)

        # Clamp top-left to 0
        self._actual_bounds = QRectF(
            max(0.0, min_x), max(0.0, min_y),
            max_x - min_x + doc_margin * 2,
            max_y - min_y + doc_margin * 2
        )

    # ---- draw -------------------------------------------------------------

    def draw(self, painter: QPainter, context: QAbstractTextDocumentLayout.PaintContext):
        """Draw every character independently at its path position.

        Bypasses QTextLine.draw() entirely — each character is placed with
        painter.translate / painter.rotate and rendered via drawText().  This
        is the only reliable way to get one-char-per-position rendering across
        Qt versions.
        """
        doc = self.document()
        block = doc.firstBlock()
        has_selection = len(context.selections) > 0
        selection = context.selections[0] if has_selection else None

        char_idx = 0  # index into _char_angles / _char_positions arrays

        while block.isValid():
            blpos = block.position()
            bllen = block.length()
            blk_text = block.text()
            blk_text_len = len(blk_text)

            char_fmt = block.charFormat()
            font = char_fmt.font()
            fm = QFontMetricsF(font)

            painter.setFont(font)

            for i, ch in enumerate(blk_text):
                if ch == '\n':
                    continue
                if char_idx >= len(self._char_positions):
                    # No more pre-computed positions — draw remaining flat
                    break

                pt = self._char_positions[char_idx]
                angle = self._char_angles[char_idx]

                # Selection highlight
                selected = False
                if has_selection and selection is not None:
                    sel_start = selection.cursor.selectionStart() - blpos
                    sel_end = selection.cursor.selectionEnd() - blpos
                    if i >= sel_start and i < sel_end:
                        selected = True

                painter.save()
                painter.translate(pt)
                painter.rotate(-angle)  # negate: Qt path angle is clockwise

                if selected:
                    w = fm.horizontalAdvance(ch)
                    if w <= 0:
                        w = fm.averageCharWidth()
                    h = fm.height()
                    painter.fillRect(
                        QRectF(0, -fm.ascent(), w, h),
                        QColor(0, 120, 215, 100),
                    )

                painter.drawText(QPointF(0, 0), ch)
                painter.restore()

                char_idx += 1

            block = block.next()

        # Draw cursor if editing
        if context.cursorPosition >= -1:
            self._draw_cursor(painter, context)

    def _draw_cursor(self, painter: QPainter, context: QAbstractTextDocumentLayout.PaintContext):
        """Draw a simple text cursor at the right position."""
        doc = self.document()
        block = doc.firstBlock()
        blpos = block.position()
        bllen = block.length()
        if not (blpos <= context.cursorPosition < blpos + bllen):
            return

        cpos = context.cursorPosition - blpos
        if cpos < 0 or cpos >= len(self._char_positions):
            cpos = len(self._char_positions) - 1 if self._char_positions else -1
            if cpos < 0:
                return

        pt = self._char_positions[cpos]
        angle = self._char_angles[cpos] if cpos < len(self._char_angles) else 0

        fm = QFontMetricsF(block.charFormat().font())
        cursor_h = fm.height()
        cursor_w = 2

        painter.save()
        painter.translate(pt)
        painter.rotate(-angle)
        painter.setCompositionMode(QPainter.CompositionMode.RasterOp_NotDestination)
        painter.fillRect(QRectF(0, -fm.ascent(), cursor_w, cursor_h),
                         painter.pen().brush())
        painter.restore()

    # ---- hit-test ---------------------------------------------------------

    def hitTest(self, point: QPointF, accuracy: Qt.HitTestAccuracy) -> int:
        """Map a layout-space point to a document cursor position.

        Simplified: find the nearest character position.
        """
        if not self._char_positions:
            return 0

        best_dist = float('inf')
        best_idx = 0
        for i, pt in enumerate(self._char_positions):
            dx = point.x() - pt.x()
            dy = point.y() - pt.y()
            d = dx * dx + dy * dy
            if d < best_dist:
                best_dist = d
                best_idx = i

        return self._line_to_char_idx[best_idx] if best_idx < len(self._line_to_char_idx) else 0

    def blockBoundingRect(self, block: QTextBlock) -> QRectF:
        br = block.layout().boundingRect()
        return QRectF(0, 0, br.width(), br.height())
