"""
Worker de aquisição e processamento em thread separada (QThread).

Captura frames da webcam, detecta o rosto, extrai a média RGB de ROIs de pele,
mantém um buffer deslizante, roda o ensemble rPPG e emite os resultados para a
interface via sinais Qt. Toda a UI permanece responsiva.
"""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import List, Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from . import dsp
from .dsp import Estimativa

JANELA_SEG = 8
N_MAX = int(JANELA_SEG * 60)


@dataclass
class Amostra:
    """Pacote de dados emitido a cada frame processado."""
    frame_rgb: np.ndarray                      # frame anotado (RGB, para Qt)
    bpm: float = 0.0
    sqi: float = 0.0
    ok: bool = False
    batida: bool = False
    rosto: bool = False
    progresso: float = 0.0                      # 0..1 enquanto enche o buffer
    fps: float = 0.0
    hist: List[float] = field(default_factory=list)
    est: Optional[Estimativa] = None


class RppgWorker(QThread):
    """Thread de captura + processamento rPPG."""

    amostra = pyqtSignal(object)               # Amostra
    erro = pyqtSignal(str)
    estado = pyqtSignal(str)                    # mensagens de status

    def __init__(self, indice_camera: int = 0, parent=None):
        super().__init__(parent)
        self.indice_camera = indice_camera
        self._rodando = False
        self._gravando = False
        self._registros: List[list] = []
        self._face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml")

    # ---- controle externo (thread-safe o suficiente p/ flags simples) ----

    def parar(self):
        self._rodando = False

    def gravando(self) -> bool:
        return self._gravando

    def iniciar_gravacao(self):
        self._registros = []
        self._gravando = True

    def encerrar_gravacao(self) -> List[list]:
        self._gravando = False
        return self._registros

    # ---- loop principal ----

    def run(self):
        cap = cv2.VideoCapture(self.indice_camera)
        if not cap.isOpened():
            self.erro.emit(f"Não foi possível abrir a câmera {self.indice_camera}.")
            return

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        rgb_buf = deque(maxlen=N_MAX)
        t_buf = deque(maxlen=N_MAX)
        bpm_recent = deque(maxlen=7)
        bpm_hist = deque(maxlen=300)
        est = Estimativa()
        bpm = sqi = 0.0
        ultima_batida = 0.0
        box = None
        sem_rosto = 0
        verde_ant = None
        t0 = time.time()
        ultimo_hist = 0.0
        fps = 0.0
        t_prev = time.time()

        self._rodando = True
        self.estado.emit("Mantenha o rosto iluminado e parado por ~8 s.")

        while self._rodando:
            ok, frame = cap.read()
            if not ok:
                self.erro.emit("Falha ao ler frame da câmera.")
                break

            frame = cv2.flip(frame, 1)
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            faces = self._face_cascade.detectMultiScale(
                gray, 1.3, 5, minSize=(120, 120))

            if len(faces):
                det = max(faces, key=lambda f: f[2] * f[3]).astype(float)
                box = det if box is None else 0.6 * box + 0.4 * det
                sem_rosto = 0
            else:
                sem_rosto += 1
                if sem_rosto > 30:
                    box = None

            tem_rosto = box is not None
            if tem_rosto:
                x, y, w, h = box.astype(int)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (70, 160, 200), 1)
                rois = [
                    (x + int(w * 0.30), y + int(h * 0.07), int(w * 0.40), int(h * 0.18)),
                    (x + int(w * 0.12), y + int(h * 0.55), int(w * 0.22), int(h * 0.22)),
                    (x + int(w * 0.66), y + int(h * 0.55), int(w * 0.22), int(h * 0.22)),
                ]
                medias = []
                for (rx, ry, rw, rh) in rois:
                    cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh),
                                  (150, 220, 130), 1)
                    m = dsp.media_roi(frame, rx, ry, rw, rh)
                    if m is not None:
                        medias.append(m)
                if medias:
                    rgb = np.mean(medias, axis=0)
                    if verde_ant is None or abs(rgb[1] - verde_ant) < 8.0:
                        rgb_buf.append(rgb)
                        t_buf.append(time.time() - t0)
                    verde_ant = rgb[1]

            # estimativa quando há histórico suficiente
            if len(rgb_buf) >= int(dsp.FS_ALVO * 4):
                try:
                    rgb_u, fs = dsp.reamostra_uniforme(t_buf, np.array(rgb_buf))
                    est = dsp.estima_ensemble(rgb_u, fs)
                    sqi = est.sqi
                    bpm_inst = est.bpm
                    if dsp.BPM_MIN <= bpm_inst <= dsp.BPM_MAX and sqi >= 0.4:
                        if (not bpm_recent or
                                abs(bpm_inst - np.median(bpm_recent)) < 15):
                            bpm_recent.append(bpm_inst)
                    if bpm_recent:
                        bpm = float(np.median(bpm_recent))
                except Exception:
                    pass

            ok_bpm = (dsp.BPM_MIN <= bpm <= dsp.BPM_MAX and sqi >= 0.4
                      and len(bpm_recent) >= 2)

            agora = time.time()
            batida = False
            if ok_bpm and bpm > 0 and (agora - ultima_batida) >= (60.0 / bpm):
                ultima_batida = agora
                batida = True

            if ok_bpm and (not bpm_hist or agora - ultimo_hist >= 1.0):
                bpm_hist.append(bpm)
                ultimo_hist = agora

            if self._gravando:
                self._registros.append([
                    round(agora - t0, 2), round(bpm, 1), round(est.snr, 2),
                    round(sqi, 3), round(est.hrv, 1), round(est.bpm_ac, 1),
                ])

            # fps suavizado
            dt = agora - t_prev
            t_prev = agora
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt

            progresso = min(len(rgb_buf) / (dsp.FS_ALVO * 4), 1.0)
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            self.amostra.emit(Amostra(
                frame_rgb=frame_rgb, bpm=bpm, sqi=sqi, ok=ok_bpm, batida=batida,
                rosto=tem_rosto, progresso=progresso, fps=fps,
                hist=list(bpm_hist), est=est,
            ))

        cap.release()
