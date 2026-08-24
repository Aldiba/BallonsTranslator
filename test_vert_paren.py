import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
from qtpy.QtCore import Qt, QRectF
from qtpy.QtGui import (QTextDocument, QFont, QPainter, QImage, QFontMetricsF,
                        QAbstractTextDocumentLayout)
from qtpy.QtWidgets import QApplication

from utils.fontformat import FontFormat
from ui.scene_textlayout import VerticalTextDocumentLayout

app = QApplication.instance() or QApplication([])
print('app devicePixelRatio:', app.devicePixelRatio())
from qtpy.QtGui import QGuiApplication
print('app DPI (logical):', QGuiApplication.primaryScreen().logicalDotsPerInch())

# 基础字体度量
fm = QFontMetricsF(QFont('Microsoft YaHei', 30))
for ch in ['我', '爱', '「', '《', '（', '」', '》', '）']:
    tbr = fm.tightBoundingRect(ch)
    br = fm.boundingRect(ch)
    print(f'{ch}: tight={tbr.x():.1f},{tbr.y():.1f} {tbr.width():.1f}x{tbr.height():.1f} | bounds={br.x():.1f},{br.y():.1f} {br.width():.1f}x{br.height():.1f} | adv={fm.horizontalAdvance(ch):.1f}')
print(f'ascent={fm.ascent():.1f} descent={fm.descent():.1f} height={fm.height():.1f}')

_kept = None
def build(text, font_size=60, w=400, h=600):
    global _kept
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    ff = FontFormat(font_family='Microsoft YaHei', font_size=font_size,
                    vertical=True, frgb=[0,0,0,255])
    layout = VerticalTextDocumentLayout(doc, ff)
    doc.setDocumentLayout(layout)
    layout.setMaxSize(w, h)
    doc.setPlainText(text)
    layout.reLayoutEverything()
    _kept = (doc, ff, layout)
    return doc, ff, layout

def dump(text):
    doc, ff, layout = build(text)
    blk = doc.firstBlock()
    tl = blk.layout()
    blk_text = blk.text()
    ls_lst = layout.line_spaces_lst[0]
    offsets = layout._draw_offset[0]
    print(f'=== {text} ===')
    for ii in range(tl.lineCount()):
        ln = tl.lineAt(ii)
        if ln.textLength() == 0: continue
        char_idx = min(ls_lst[ii][3] + ls_lst[ii][1], len(blk_text)-1)
        ch = blk_text[char_idx]
        xoff, yoff = offsets[ii]
        cfmt = layout.get_char_fontfmt(0, char_idx)
        print(f'  idx{ii} char={ch!r} line.y={ln.y():.2f} line.x={ln.x():.2f} off=({xoff:.2f},{yoff:.2f}) '
              f'ascent={ln.ascent():.2f} ntw={ln.naturalTextWidth():.2f}')
    print()

dump('我爱你')
dump('我爱《你》')
dump('他「说」话')
