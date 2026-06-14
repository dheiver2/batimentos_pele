"""Enumeração de câmeras disponíveis."""

from __future__ import annotations

from typing import List, Tuple

import cv2


def listar_cameras(maximo: int = 5) -> List[Tuple[int, str]]:
    """Tenta abrir índices 0..maximo-1 e retorna os disponíveis."""
    achadas = []
    for i in range(maximo):
        cap = cv2.VideoCapture(i)
        if cap is not None and cap.isOpened():
            achadas.append((i, f"Câmera {i}"))
            cap.release()
    if not achadas:
        achadas = [(0, "Câmera 0")]
    return achadas
