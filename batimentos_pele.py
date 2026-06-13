"""
Detecção de batimentos cardíacos por variação de tons de pele (rPPG).

A cada batimento, o sangue muda sutilmente a cor da pele do rosto. Capturamos
isso pela webcam: medimos a média do canal verde na testa ao longo do tempo,
filtramos a faixa de frequência cardíaca (0.7-3 Hz = 42-180 bpm) e estimamos
os BPM. Uma janela mostra o vídeo + um gráfico do sinal pulsátil ao vivo.

Requisitos:
    pip install opencv-python numpy scipy

Uso:
    python batimentos_pele.py      (pressione 'q' para sair)
"""

import time
from collections import deque

import cv2
import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

# ----- Parâmetros -----
FPS_ALVO = 30
JANELA_SEG = 10                      # segundos de histórico para análise
N = FPS_ALVO * JANELA_SEG
FREQ_MIN, FREQ_MAX = 0.7, 3.0        # Hz -> 42 a 180 bpm
LARGURA_GRAFICO = 400
ALTURA_GRAFICO = 150


def filtro_passa_banda(sinal, fs, low=FREQ_MIN, high=FREQ_MAX, ordem=3):
    nyq = 0.5 * fs
    b, a = butter(ordem, [low / nyq, high / nyq], btype="band")
    return filtfilt(b, a, sinal)


def estima_bpm(sinal, fs):
    """Estima BPM via FFT na faixa cardíaca."""
    sinal = sinal - np.mean(sinal)
    fft = np.abs(np.fft.rfft(sinal))
    freqs = np.fft.rfftfreq(len(sinal), 1.0 / fs)
    mask = (freqs >= FREQ_MIN) & (freqs <= FREQ_MAX)
    if not np.any(mask):
        return 0.0
    pico = freqs[mask][np.argmax(fft[mask])]
    return pico * 60.0


def desenha_grafico(sinal):
    """Renderiza o sinal pulsátil como uma imagem."""
    img = np.zeros((ALTURA_GRAFICO, LARGURA_GRAFICO, 3), dtype=np.uint8)
    if len(sinal) < 2:
        return img
    s = np.array(sinal[-LARGURA_GRAFICO:])
    s = s - s.min()
    if s.max() > 0:
        s = s / s.max()
    pts = []
    for i, v in enumerate(s):
        x = int(i * LARGURA_GRAFICO / len(s))
        y = int(ALTURA_GRAFICO - 1 - v * (ALTURA_GRAFICO - 10) - 5)
        pts.append((x, y))
    for i in range(1, len(pts)):
        cv2.line(img, pts[i - 1], pts[i], (0, 255, 120), 1)
    return img


def main():
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Erro: não foi possível acessar a webcam.")
        return

    valores = deque(maxlen=N)
    tempos = deque(maxlen=N)
    bpm = 0.0
    t0 = time.time()

    print("Detectando batimentos... mantenha o rosto na câmera. 'q' para sair.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5, minSize=(120, 120))

        if len(faces) > 0:
            x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
            cv2.rectangle(frame, (x, y), (x + w, y + h), (230, 180, 0), 2)

            # ROI = testa (faixa superior central do rosto)
            fx = x + int(w * 0.30)
            fy = y + int(h * 0.08)
            fw = int(w * 0.40)
            fh = int(h * 0.20)
            cv2.rectangle(frame, (fx, fy), (fx + fw, fy + fh), (0, 220, 0), 2)
            roi = frame[fy:fy + fh, fx:fx + fw]

            if roi.size > 0:
                # canal verde é o mais sensível ao volume sanguíneo
                verde = np.mean(roi[:, :, 1])
                valores.append(verde)
                tempos.append(time.time() - t0)

        # estima BPM quando há histórico suficiente
        sinal_filtrado = []
        if len(valores) >= FPS_ALVO * 4:
            dur = tempos[-1] - tempos[0]
            fs = len(tempos) / dur if dur > 0 else FPS_ALVO
            try:
                sinal_filtrado = filtro_passa_banda(np.array(valores), fs)
                bpm = estima_bpm(sinal_filtrado, fs)
            except Exception:
                pass

        # overlay do BPM
        cor = (0, 255, 0) if 40 <= bpm <= 180 else (0, 165, 255)
        cv2.putText(frame, f"{bpm:5.1f} BPM", (20, 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.1, cor, 2)
        cv2.putText(frame, "Detectando pulso pela cor da pele (rPPG)",
                    (20, frame.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (200, 200, 200), 1)

        if len(sinal_filtrado) > 0:
            graf = desenha_grafico(sinal_filtrado)
            gh, gw = graf.shape[:2]
            frame[10:10 + gh, frame.shape[1] - gw - 10:frame.shape[1] - 10] = graf

        cv2.imshow("Batimentos pela Pele - rPPG", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
