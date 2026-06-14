"""
Detecção de face landmarks de alta precisão via MediaPipe Face Mesh
(FaceLandmarker, 478 pontos 3D) para extração de ROIs de pele.

Em rPPG, a maior fonte de ruído depois do movimento é uma ROI imprecisa.
Caixas fixas (Haar) incluem cabelo, olhos e fundo; landmarks acompanham o
rosto pixel a pixel, permitindo isolar testa e bochechas — onde o sinal de
pulso é mais forte e estável.

O modelo (~3.8 MB) é baixado sob demanda para ~/.cache/vitalscan/. Se o
MediaPipe ou o modelo não estiverem disponíveis, `criar()` devolve None e o
sistema usa o detector Haar como fallback.
"""

from __future__ import annotations

import os
import urllib.request
from typing import List, Optional, Tuple

import numpy as np

MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
             "face_landmarker/float16/1/face_landmarker.task")

# Índices de landmarks (topologia de 478 pontos) que delimitam regiões de pele.
# Convex hull de cada conjunto -> polígono da ROI.
ROI_TESTA = [67, 69, 109, 10, 338, 299, 297, 332, 103, 104, 105, 334, 333]
ROI_BOCHECHA_ESQ = [50, 101, 118, 117, 123, 147, 187, 205, 36, 142, 126]
ROI_BOCHECHA_DIR = [280, 330, 347, 346, 352, 376, 411, 425, 266, 371, 355]
# Contorno facial (oval) — apenas para desenho na UI.
OVAL = [10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365,
        379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93,
        234, 127, 162, 21, 54, 103, 67, 109]


def _caminho_modelo() -> str:
    env = os.environ.get("VITALSCAN_FACE_MODEL")
    if env and os.path.exists(env):
        return env
    cache = os.path.join(os.path.expanduser("~"), ".cache", "vitalscan")
    os.makedirs(cache, exist_ok=True)
    destino = os.path.join(cache, "face_landmarker.task")
    if not os.path.exists(destino):
        urllib.request.urlretrieve(MODEL_URL, destino)
    return destino


class MalhaFacial:
    """Wrapper do FaceLandmarker em modo vídeo (rastreamento temporal)."""

    def __init__(self, model_path: str):
        import mediapipe as mp
        from mediapipe.tasks import python
        from mediapipe.tasks.python import vision

        self._mp = mp
        base = python.BaseOptions(model_asset_path=model_path)
        opt = vision.FaceLandmarkerOptions(
            base_options=base,
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            min_face_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._lmk = vision.FaceLandmarker.create_from_options(opt)
        self._ultimo_ts = -1

    @staticmethod
    def criar() -> "Optional[MalhaFacial]":
        """Tenta instanciar; devolve None se MediaPipe/modelo indisponível."""
        try:
            return MalhaFacial(_caminho_modelo())
        except Exception:
            return None

    def detecta(self, frame_bgr: np.ndarray, ts_ms: int):
        """Retorna array (478,2) de pixels (x,y) ou None."""
        import cv2
        # o modo VIDEO exige timestamps estritamente crescentes
        if ts_ms <= self._ultimo_ts:
            ts_ms = self._ultimo_ts + 1
        self._ultimo_ts = ts_ms
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        res = self._lmk.detect_for_video(mp_img, ts_ms)
        if not res.face_landmarks:
            return None
        h, w = frame_bgr.shape[:2]
        lm = res.face_landmarks[0]
        return np.array([[p.x * w, p.y * h] for p in lm], dtype=np.float32)


def media_roi_poligono(frame, pts_roi) -> Optional[np.ndarray]:
    """Média RGB sobre pixels de pele dentro do convex hull dos pontos."""
    import cv2
    h_img, w_img = frame.shape[:2]
    hull = cv2.convexHull(pts_roi.astype(np.int32))
    mask = np.zeros((h_img, w_img), np.uint8)
    cv2.fillConvexPoly(mask, hull, 255)
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    pele = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    mask = cv2.bitwise_and(mask, pele)
    px = frame[mask > 0]
    if len(px) < 50:
        hull_px = frame[cv2.fillConvexPoly(
            np.zeros((h_img, w_img), np.uint8), hull, 255) > 0]
        if len(hull_px) < 20:
            return None
        px = hull_px
    b, g, r = px[:, 0].mean(), px[:, 1].mean(), px[:, 2].mean()
    return np.array([r, g, b])


def extrai_rgb(frame, pontos) -> Optional[np.ndarray]:
    """Média das 3 ROIs de pele (testa + 2 bochechas) a partir dos landmarks."""
    medias = []
    for idx in (ROI_TESTA, ROI_BOCHECHA_ESQ, ROI_BOCHECHA_DIR):
        m = media_roi_poligono(frame, pontos[idx])
        if m is not None:
            medias.append(m)
    if not medias:
        return None
    return np.mean(medias, axis=0)


def desenha(frame, pontos):
    """Desenha contorno facial, polígonos das ROIs e malha esparsa de pontos."""
    import cv2
    # contorno facial
    oval = cv2.convexHull(pontos[OVAL].astype(np.int32))
    cv2.polylines(frame, [oval], True, (70, 160, 200), 1, cv2.LINE_AA)
    # polígonos das ROIs
    for idx in (ROI_TESTA, ROI_BOCHECHA_ESQ, ROI_BOCHECHA_DIR):
        hull = cv2.convexHull(pontos[idx].astype(np.int32))
        cv2.polylines(frame, [hull], True, (150, 220, 130), 1, cv2.LINE_AA)
    # malha esparsa (1 a cada 6 pontos) para feedback visual
    for (x, y) in pontos[::6].astype(int):
        cv2.circle(frame, (x, y), 1, (90, 130, 90), -1, cv2.LINE_AA)
