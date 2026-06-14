"""Widgets customizados do VitalScan (gauge, cards, pills, vídeo, plots)."""

from __future__ import annotations

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import (QEasingCurve, QPropertyAnimation, QRectF, Qt,
                          pyqtProperty)
from PyQt6.QtGui import (QColor, QFont, QImage, QPainter, QPainterPath, QPen,
                         QPixmap)
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                             QVBoxLayout, QWidget)

from . import theme

pg.setConfigOptions(antialias=True, background=theme.BG, foreground=theme.FAINT)


def _qcolor(hexstr: str) -> QColor:
    return QColor(hexstr)


# --------------------------------------------------------------------------- #
#  Cartão base
# --------------------------------------------------------------------------- #

class Card(QFrame):
    """Painel arredondado com título opcional."""

    def __init__(self, titulo: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("card")
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(18, 14, 18, 14)
        self._lay.setSpacing(8)
        if titulo:
            lbl = QLabel(titulo)
            lbl.setObjectName("cardTitle")
            self._lay.addWidget(lbl)

    def add(self, w):
        self._lay.addWidget(w)
        return w

    def add_layout(self, lay):
        self._lay.addLayout(lay)
        return lay


# --------------------------------------------------------------------------- #
#  Gauge circular animado de frequência cardíaca
# --------------------------------------------------------------------------- #

class HeartGauge(QWidget):
    """Anel de progresso + valor de BPM, com batida animada."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(220, 220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self._bpm = 0.0
        self._frac = 0.0
        self._ok = False
        self._pulse = 0.0
        self._anim = QPropertyAnimation(self, b"frac", self)
        self._anim.setDuration(450)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._pulse_anim = QPropertyAnimation(self, b"pulse", self)
        self._pulse_anim.setDuration(320)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.OutQuad)

    # propriedade animável: fração do anel
    def getFrac(self): return self._frac
    def setFrac(self, v): self._frac = v; self.update()
    frac = pyqtProperty(float, getFrac, setFrac)

    def getPulse(self): return self._pulse
    def setPulse(self, v): self._pulse = v; self.update()
    pulse = pyqtProperty(float, getPulse, setPulse)

    def set_valor(self, bpm: float, ok: bool):
        self._bpm = bpm
        self._ok = ok
        alvo = float(np.clip((bpm - 40) / 140.0, 0, 1)) if ok else 0.0
        self._anim.stop()
        self._anim.setStartValue(self._frac)
        self._anim.setEndValue(alvo)
        self._anim.start()

    def batida(self):
        self._pulse_anim.stop()
        self._pulse_anim.setStartValue(1.0)
        self._pulse_anim.setEndValue(0.0)
        self._pulse_anim.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        side = min(w, h) - 30
        cx, cy = w / 2, h / 2
        rect = QRectF(cx - side / 2, cy - side / 2, side, side)
        esp = max(2.0, side * 0.018)          # anel fino, elegante

        cor = _qcolor(theme.ACC if self._ok else theme.MUT)

        # trilho discreto
        pen = QPen(_qcolor(theme.LINE), esp, cap=Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, 0, 360 * 16)

        # progresso (começa no topo, sentido horário)
        if self._frac > 0:
            pen = QPen(cor, esp, cap=Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawArc(rect, 90 * 16, int(-self._frac * 360 * 16))

        # valor — número herói, peso leve
        p.setPen(_qcolor(theme.TXT if self._ok else theme.MUT))
        f = QFont()
        f.setPointSizeF(side * 0.26)
        f.setWeight(QFont.Weight.Light)
        p.setFont(f)
        valor = f"{self._bpm:.0f}" if self._ok else "--"
        p.drawText(QRectF(cx - side / 2, cy - side * 0.20, side, side * 0.42),
                   Qt.AlignmentFlag.AlignCenter, valor)

        # coração pulsante + "bpm" na base
        scale = 1.0 + 0.22 * self._pulse
        self._draw_heart(p, cx - side * 0.07, cy + side * 0.20,
                         side * 0.035 * scale, cor)
        p.setPen(_qcolor(theme.MUT))
        f2 = QFont(); f2.setPointSizeF(side * 0.05)
        f2.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2.0)
        p.setFont(f2)
        p.drawText(QRectF(cx - side / 2 + side * 0.10, cy + side * 0.155,
                          side, side * 0.10),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                   "BPM")
        p.end()

    @staticmethod
    def _draw_heart(p: QPainter, cx, cy, s, cor):
        path = QPainterPath()
        path.moveTo(cx, cy + s * 0.5)
        path.cubicTo(cx + s * 1.3, cy - s * 0.6,
                     cx + s * 0.4, cy - s * 1.2, cx, cy - s * 0.35)
        path.cubicTo(cx - s * 0.4, cy - s * 1.2,
                     cx - s * 1.3, cy - s * 0.6, cx, cy + s * 0.5)
        p.fillPath(path, cor)


# --------------------------------------------------------------------------- #
#  Card de métrica (valor grande + barra opcional)
# --------------------------------------------------------------------------- #

class MetricCard(Card):
    def __init__(self, titulo: str, unidade: str, cor: str, barra=False):
        super().__init__(titulo)
        self._cor = cor
        self._barra = barra
        linha = QHBoxLayout()
        linha.setSpacing(6)
        self.valor = QLabel("--")
        self.valor.setObjectName("metricBig")
        self.valor.setStyleSheet(f"color: {cor};")
        un = QLabel(unidade)
        un.setObjectName("metricUnit")
        linha.addWidget(self.valor)
        linha.addWidget(un, alignment=Qt.AlignmentFlag.AlignBottom)
        linha.addStretch()
        self.add_layout(linha)
        if barra:
            self.bar = ProgressBar(cor)
            self.add(self.bar)

    def set(self, texto: str, frac: float = None):
        self.valor.setText(texto)
        if self._barra and frac is not None:
            self.bar.set_frac(frac)


class ProgressBar(QWidget):
    def __init__(self, cor: str):
        super().__init__()
        self._cor = cor
        self._frac = 0.0
        self.setFixedHeight(3)

    def set_frac(self, v):
        self._frac = float(np.clip(v, 0, 1))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_qcolor(theme.LINE))
        p.drawRoundedRect(QRectF(r), 1.5, 1.5)
        p.setBrush(_qcolor(self._cor))
        p.drawRoundedRect(QRectF(0, 0, r.width() * self._frac, r.height()), 1.5, 1.5)
        p.end()


# --------------------------------------------------------------------------- #
#  Pílula de status
# --------------------------------------------------------------------------- #

class StatusPill(QLabel):
    def __init__(self, texto="", cor=theme.MUT):
        super().__init__(texto)
        self.set_estado(texto, cor)

    def set_estado(self, texto: str, cor: str):
        self.setText(f"●  {texto}")
        self.setStyleSheet(
            f"color: {cor}; font-size: 11px; font-weight: 700;"
            f"letter-spacing: 1px; background: transparent; padding: 4px 2px;")


# --------------------------------------------------------------------------- #
#  Visualização da câmera
# --------------------------------------------------------------------------- #

class VideoView(QLabel):
    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 270)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,
                           QSizePolicy.Policy.Expanding)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            f"background: {theme.PANEL}; border: 1px solid {theme.LINE};"
            f"border-radius: 14px; color: {theme.FAINT}; font-size: 12px;"
            f"letter-spacing: 1px;")
        self.setText("CÂMERA DESLIGADA")

    def set_frame(self, rgb: np.ndarray):
        h, w, _ = rgb.shape
        img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888)
        pix = QPixmap.fromImage(img).scaled(
            self.size(), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation)
        self.setPixmap(pix)


# --------------------------------------------------------------------------- #
#  Plots (pyqtgraph)
# --------------------------------------------------------------------------- #

class WaveformPlot(pg.PlotWidget):
    """Pletismograma — sinal de pulso óptico ao vivo."""

    def __init__(self):
        super().__init__()
        self.setBackground(theme.BG)
        self.setMenuEnabled(False)
        self.setMouseEnabled(False, False)
        self.hideButtons()
        self.getPlotItem().hideAxis("left")
        self.getPlotItem().hideAxis("bottom")
        self._curve = self.plot(pen=pg.mkPen(theme.ACC, width=1.6))

    def set_sinal(self, sig: np.ndarray, ok: bool):
        if sig is None or len(sig) < 2:
            self._curve.setData([])
            return
        s = np.asarray(sig, float)
        s = s - s.mean()
        amp = np.max(np.abs(s)) or 1.0
        cor = theme.ACC if ok else theme.WARN
        self._curve.setPen(pg.mkPen(cor, width=1.6))
        self._curve.setData(s / amp)
        self.setYRange(-1.1, 1.1, padding=0)


class TrendPlot(pg.PlotWidget):
    """Tendência de BPM ao longo do tempo."""

    def __init__(self):
        super().__init__()
        self.setBackground(theme.BG)
        self.setMenuEnabled(False)
        self.setMouseEnabled(False, False)
        self.hideButtons()
        self.getPlotItem().hideAxis("bottom")
        self.getPlotItem().hideAxis("left")
        self.setYRange(45, 150)
        self._curve = self.plot(
            pen=pg.mkPen(theme.ACC, width=1.6),
            fillLevel=45, brush=pg.mkBrush(92, 240, 138, 22))

    def set_hist(self, hist):
        if not hist:
            self._curve.setData([])
            return
        self._curve.setData(np.asarray(hist, float))
