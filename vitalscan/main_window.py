"""Janela principal do VitalScan."""

from __future__ import annotations

import csv
import time

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QFrame, QGridLayout,
                             QHBoxLayout, QLabel, QMainWindow, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from . import __app_name__, __version__, theme
from .cameras import listar_cameras
from .widgets import (Card, HeartGauge, MetricCard, StatusPill, TrendPlot,
                      VideoView, WaveformPlot)
from .worker import Amostra, RppgWorker


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{__app_name__} — rPPG")
        self.resize(1300, 820)
        self.worker: RppgWorker | None = None
        self._ultima: Amostra | None = None

        self._build_ui()
        self._build_atalhos()

        # relógio do cabeçalho
        self._relogio = QTimer(self)
        self._relogio.timeout.connect(self._tick_relogio)
        self._relogio.start(1000)

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(34, 26, 34, 20)
        outer.setSpacing(22)

        outer.addLayout(self._build_header())
        outer.addWidget(self._hairline())

        grid = QGridLayout()
        grid.setHorizontalSpacing(34)
        grid.setVerticalSpacing(22)
        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 4)
        grid.setColumnStretch(2, 4)

        # --- câmera ---
        cam_card = Card("CÂMERA / ROI")
        self.video = VideoView()
        cam_card.add(self.video)
        grid.addWidget(cam_card, 0, 0, 2, 1)

        # --- gauge HR ---
        hr_card = Card("FREQUÊNCIA CARDÍACA")
        self.gauge = HeartGauge()
        hr_card.add(self.gauge)
        self.trend = TrendPlot()
        self.trend.setFixedHeight(54)
        hr_card.add(self.trend)
        grid.addWidget(hr_card, 0, 1, 2, 1)

        # --- coluna de métricas ---
        self.card_sqi = MetricCard("QUALIDADE DO SINAL (SQI)", "%", theme.ACC_B, barra=True)
        self.card_hrv = MetricCard("VARIABILIDADE (HRV / SDNN)", "ms", theme.ACC_P)
        self.card_val = self._build_val_card()
        grid.addWidget(self.card_sqi, 0, 2)
        grid.addWidget(self.card_hrv, 1, 2)

        outer.addLayout(grid, stretch=3)

        # validação (linha própria, fina) + pleth
        outer.addWidget(self.card_val)
        outer.addWidget(self._hairline())

        pleth_card = Card("PLETISMOGRAMA")
        self.wave = WaveformPlot()
        pleth_card.add(self.wave)
        outer.addWidget(pleth_card, stretch=2)

        outer.addLayout(self._build_footer())

    def _hairline(self):
        ln = QFrame()
        ln.setFixedHeight(1)
        ln.setStyleSheet(f"background: {theme.LINE}; border: none;")
        return ln

    def _build_header(self):
        h = QHBoxLayout()
        h.setSpacing(12)
        brand = QLabel("VITALSCAN")
        brand.setObjectName("brand")
        sub = QLabel("rPPG · monitor de pulso óptico")
        sub.setObjectName("brandSub")
        col = QVBoxLayout(); col.setSpacing(0)
        col.addWidget(brand); col.addWidget(sub)
        h.addLayout(col)
        h.addStretch()

        self.cmb_cam = QComboBox()
        for idx, nome in listar_cameras():
            self.cmb_cam.addItem(nome, idx)
        h.addWidget(self.cmb_cam)

        self.btn_start = QPushButton("Iniciar")
        self.btn_start.setObjectName("primary")
        self.btn_start.clicked.connect(self.toggle_captura)
        h.addWidget(self.btn_start)

        self.btn_rec = QPushButton("● Gravar")
        self.btn_rec.setObjectName("danger")
        self.btn_rec.setEnabled(False)
        self.btn_rec.clicked.connect(self.toggle_gravacao)
        h.addWidget(self.btn_rec)

        self.pill = StatusPill("DESLIGADO", theme.MUT)
        h.addWidget(self.pill)

        self.lbl_relogio = QLabel(time.strftime("%H:%M:%S"))
        self.lbl_relogio.setStyleSheet(f"color:{theme.TXT}; font-size:14px;")
        h.addWidget(self.lbl_relogio)
        return h

    def _build_val_card(self):
        card = Card("VALIDAÇÃO CRUZADA")
        linha = QHBoxLayout()
        self.lbl_m1 = QLabel("—")
        self.lbl_m2 = QLabel("—")
        for w in (self.lbl_m1, self.lbl_m2):
            w.setStyleSheet(f"color:{theme.TXT}; font-size:14px; font-weight:600;")
        self.lbl_conf = StatusPill("AGUARDANDO", theme.MUT)
        self.lbl_acordo = QLabel("concordância métodos / FFT≈autocorr: —")
        self.lbl_acordo.setStyleSheet(f"color:{theme.MUT}; font-size:11px;")
        linha.addWidget(self.lbl_m1)
        linha.addWidget(self.lbl_m2)
        linha.addStretch()
        linha.addWidget(self.lbl_acordo)
        linha.addWidget(self.lbl_conf)
        card.add_layout(linha)
        return card

    def _build_footer(self):
        f = QHBoxLayout()
        av = QLabel("Demonstração educativa — não é dispositivo médico.")
        av.setObjectName("footer")
        self.lbl_fps = QLabel("")
        self.lbl_fps.setObjectName("footer")
        f.addWidget(av)
        f.addStretch()
        f.addWidget(self.lbl_fps)
        ver = QLabel(f"v{__version__}")
        ver.setObjectName("footer")
        f.addWidget(ver)
        return f

    def _build_atalhos(self):
        QShortcut(QKeySequence("Space"), self, self.toggle_captura)
        QShortcut(QKeySequence("R"), self, self.toggle_gravacao)
        QShortcut(QKeySequence("Q"), self, self.close)

    # ------------------------------------------------------------- captura
    def toggle_captura(self):
        if self.worker and self.worker.isRunning():
            self._parar()
        else:
            self._iniciar()

    def _iniciar(self):
        idx = self.cmb_cam.currentData() or 0
        self.worker = RppgWorker(indice_camera=idx)
        self.worker.amostra.connect(self.on_amostra)
        self.worker.erro.connect(self.on_erro)
        self.worker.estado.connect(lambda s: self.pill.set_estado("INICIANDO", theme.ACC_B))
        self.worker.start()
        self.btn_start.setText("Parar")
        self.btn_rec.setEnabled(True)
        self.cmb_cam.setEnabled(False)
        self.pill.set_estado("INICIANDO", theme.ACC_B)

    def _parar(self):
        if self.worker:
            if self.worker.gravando():
                self.toggle_gravacao()
            self.worker.parar()
            self.worker.wait(2000)
            self.worker = None
        self.btn_start.setText("Iniciar")
        self.btn_rec.setEnabled(False)
        self.cmb_cam.setEnabled(True)
        self.pill.set_estado("DESLIGADO", theme.MUT)
        self.video.setText("Câmera desligada")
        self.video.setPixmap(self.video.pixmap() or self.video.pixmap())

    # ------------------------------------------------------------- gravação
    def toggle_gravacao(self):
        if not (self.worker and self.worker.isRunning()):
            return
        if self.worker.gravando():
            registros = self.worker.encerrar_gravacao()
            self.btn_rec.setText("● Gravar")
            self._salvar_csv(registros)
        else:
            self.worker.iniciar_gravacao()
            self.btn_rec.setText("■ Parar gravação")

    def _salvar_csv(self, registros):
        if not registros:
            return
        nome = time.strftime("rppg_%Y%m%d_%H%M%S.csv")
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar gravação", nome, "CSV (*.csv)")
        if not caminho:
            return
        with open(caminho, "w", newline="") as fp:
            w = csv.writer(fp)
            w.writerow(["t_s", "bpm", "snr_db", "sqi", "hrv_ms", "bpm_autocorr"])
            w.writerows(registros)
        QMessageBox.information(self, "Gravação salva",
                               f"{len(registros)} amostras salvas em:\n{caminho}")

    # ------------------------------------------------------------- callbacks
    def on_amostra(self, a: Amostra):
        self._ultima = a
        self.video.set_frame(a.frame_rgb)
        self.gauge.set_valor(a.bpm, a.ok)
        if a.batida:
            self.gauge.batida()
        self.trend.set_hist(a.hist)

        est = a.est
        self.card_sqi.set(f"{a.sqi*100:.0f}", a.sqi)
        self.card_hrv.set(f"{est.hrv:.0f}" if a.ok and est.hrv > 0 else "--")
        self.wave.set_sinal(est.sig, a.ok)

        self.lbl_m1.setText(f"{est.melhor} {est.bpm_m1:.0f}")
        self.lbl_m2.setText(f"{est.segundo} {est.bpm_m2:.0f}")
        self.lbl_acordo.setText(
            f"concordância métodos / FFT≈autocorr: "
            f"{est.acordo_met*100:.0f}% / {est.acordo_ac*100:.0f}%")
        if a.ok and est.confirmado:
            self.lbl_conf.set_estado("CONFIRMADO", theme.ACC)
        elif a.ok:
            self.lbl_conf.set_estado("DIVERGENTE", theme.WARN)
        else:
            self.lbl_conf.set_estado("AGUARDANDO", theme.MUT)

        # status principal
        if not a.rosto:
            self.pill.set_estado("SEM ROSTO", theme.WARN)
        elif a.progresso < 1.0:
            self.pill.set_estado(f"CALIBRANDO {a.progresso*100:.0f}%", theme.ACC_B)
        elif a.ok:
            self.pill.set_estado("SINAL OK", theme.ACC)
        else:
            self.pill.set_estado("AJUSTANDO", theme.ACC_B)

        rec = "  ·  REC" if (self.worker and self.worker.gravando()) else ""
        modo = self.worker.modo_deteccao if self.worker else ""
        self.lbl_fps.setText(f"{modo}  ·  {a.fps:.0f} fps{rec}")

    def on_erro(self, msg: str):
        QMessageBox.critical(self, "Erro de câmera", msg)
        self._parar()

    def _tick_relogio(self):
        self.lbl_relogio.setText(time.strftime("%H:%M:%S"))

    def closeEvent(self, e):
        self._parar()
        e.accept()
