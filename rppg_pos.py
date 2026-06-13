"""
rPPG científico — estimativa de frequência cardíaca pela cor da pele.

Implementa o algoritmo POS (Plane-Orthogonal-to-Skin, Wang et al., IEEE TBME 2017),
que projeta o sinal RGB num plano ortogonal ao tom de pele para cancelar artefatos
de movimento e iluminação — bem mais robusto que a média crua do canal verde.

Recursos:
  - POS sobre múltiplas ROIs (testa + duas bochechas), combinadas
  - Índice de confiança via SNR (razão pico cardíaco / ruído no espectro)
  - BPM por FFT na faixa cardíaca + HRV (SDNN) a partir dos picos
  - Overlay com gráfico do pulso ao vivo, BPM, confiança e HRV

Requisitos:  pip3 install opencv-python numpy scipy
Uso:         python3 rppg_pos.py        ('q' para sair)

Aviso: demonstração educativa. Não é dispositivo médico.
"""

import csv
import time
from collections import deque

import cv2
import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

# ----- Parâmetros -----
JANELA_SEG = 8                       # janela deslizante para POS/FFT
FS_ALVO = 30.0                       # grade uniforme de reamostragem (Hz)
FREQ_MIN, FREQ_MAX = 0.7, 3.0        # Hz -> 42 a 180 bpm
N_MAX = int(JANELA_SEG * 60)         # buffer generoso


def reamostra_uniforme(t, y, fs=FS_ALVO):
    """Interpola sinais multicanal num grid temporal uniforme.

    A webcam entrega frames em intervalos irregulares; FFT e filtros IIR
    assumem amostragem uniforme. Sem isto, o BPM fica enviesado.
    """
    t = np.asarray(t, float)
    y = np.asarray(y, float)
    dur = t[-1] - t[0]
    n = int(dur * fs)
    if n < 8:
        return y, fs
    tu = np.linspace(t[0], t[-1], n)
    yu = np.empty((n, y.shape[1]))
    for c in range(y.shape[1]):
        yu[:, c] = np.interp(tu, t, y[:, c])
    return yu, fs


def detrend(x):
    """Remove tendência linear simples."""
    n = len(x)
    t = np.arange(n)
    a, b = np.polyfit(t, x, 1)
    return x - (a * t + b)


def pos_algorithm(rgb, fs):
    """
    POS (Wang 2017) de bloco único sobre a janela de análise.
    rgb: array (N, 3) com médias R,G,B por frame. Retorna o pulso 1D.
    """
    C = rgb.T.astype(float)                  # (3, N)
    mu = np.mean(C, axis=1, keepdims=True)   # normalização temporal
    mu[mu == 0] = 1e-8
    Cn = C / mu
    # projeção ortogonal ao tom de pele
    S1 = Cn[1] - Cn[2]                        # G - B
    S2 = Cn[1] + Cn[2] - 2 * Cn[0]           # G + B - 2R
    s2s = np.std(S2)
    alpha = np.std(S1) / s2s if s2s > 1e-8 else 0.0
    h = S1 + alpha * S2
    return h - np.mean(h)


def banda(x, fs, low=FREQ_MIN, high=FREQ_MAX, ordem=4):
    nyq = 0.5 * fs
    lo, hi = max(low / nyq, 1e-3), min(high / nyq, 0.99)
    b, a = butter(ordem, [lo, hi], btype="band")
    return filtfilt(b, a, x)


def bpm_e_snr(sinal, fs):
    """Retorna (bpm, snr_db) via FFT (com zero-padding) na faixa cardíaca."""
    sinal = (sinal - np.mean(sinal)) * np.hanning(len(sinal))
    nfft = int(2 ** np.ceil(np.log2(len(sinal) * 8)))  # zero-pad p/ resolução fina
    psd = np.abs(np.fft.rfft(sinal, n=nfft)) ** 2
    freqs = np.fft.rfftfreq(nfft, 1.0 / fs)
    mask = (freqs >= FREQ_MIN) & (freqs <= FREQ_MAX)
    if not np.any(mask):
        return 0.0, -99.0
    f_band, p_band = freqs[mask], psd[mask]
    i_pico = np.argmax(p_band)
    f_pico = f_band[i_pico]
    bpm = f_pico * 60.0
    # SNR: energia perto do pico (+1º harmônico) vs. resto da banda
    sig_mask = np.zeros_like(p_band, dtype=bool)
    for fc in (f_pico, 2 * f_pico):
        sig_mask |= np.abs(f_band - fc) <= 0.15
    sig_p = np.sum(p_band[sig_mask])
    noise_p = np.sum(p_band[~sig_mask]) + 1e-12
    snr_db = 10 * np.log10(sig_p / noise_p)
    return bpm, snr_db


def calcula_hrv(sinal, fs):
    """SDNN (ms) a partir dos intervalos entre picos."""
    sinal = (sinal - np.mean(sinal)) / (np.std(sinal) + 1e-8)
    dist = int(fs * 0.4)  # >= 0.4 s entre batimentos (<=150 bpm)
    picos, _ = find_peaks(sinal, distance=max(dist, 1), prominence=0.3)
    if len(picos) < 3:
        return 0.0
    rr = np.diff(picos) / fs * 1000.0  # ms
    return float(np.std(rr))


# ===================== Visualização estilo monitor médico =====================
# Cores no padrão de monitor de sinais vitais (BGR)
C_HR = (120, 255, 120)      # verde-lima  -> frequência cardíaca / pleth
C_CONF = (255, 230, 90)     # ciano       -> confiança/SpO2-like
C_HRV = (170, 170, 255)     # rosa/branco -> HRV
C_ALARM = (60, 60, 255)     # vermelho    -> alarme/baixa confiança
C_GRID = (40, 60, 40)       # grade ECG
C_GRID2 = (60, 90, 60)      # grade ECG (linha forte)
C_TXT = (200, 200, 200)


def desenha_grade(img, x0, y0, w, h, passo=20):
    """Grade tipo papel de ECG dentro da região (x0,y0,w,h)."""
    for i, gx in enumerate(range(x0, x0 + w, passo)):
        cv2.line(img, (gx, y0), (gx, y0 + h),
                 C_GRID2 if i % 5 == 0 else C_GRID, 1)
    for j, gy in enumerate(range(y0, y0 + h, passo)):
        cv2.line(img, (x0, gy), (x0 + w, gy),
                 C_GRID2 if j % 5 == 0 else C_GRID, 1)


def desenha_traçado(img, sinal, x0, y0, w, h, cor, sweep=0):
    """Traçado pulsátil esticado para preencher toda a largura do painel."""
    if len(sinal) < 2:
        return
    s = np.array(sinal, dtype=float)
    s = s - s.mean()
    amp = np.max(np.abs(s)) if np.max(np.abs(s)) > 1e-6 else 1.0
    s = s / amp
    # reamostra para a largura do painel
    xs = np.linspace(0, len(s) - 1, w)
    s = np.interp(xs, np.arange(len(s)), s)
    cy = y0 + h // 2
    pts = [(x0 + i, int(cy - v * (h * 0.42))) for i, v in enumerate(s)]
    for i in range(1, len(pts)):
        cv2.line(img, pts[i - 1], pts[i], cor, 2, cv2.LINE_AA)
    if pts:
        cv2.circle(img, pts[-1], 3, cor, -1, cv2.LINE_AA)


def desenha_tendencia(img, hist, x0, y0, w, h, cor, lo=40, hi=160):
    """Tendência de BPM ao longo do tempo (eixo y 40-160 bpm)."""
    # linhas de referência
    for bpm_ref in (60, 100, 140):
        yy = int(y0 + h - (bpm_ref - lo) / (hi - lo) * h)
        cv2.line(img, (x0, yy), (x0 + w, yy), (45, 45, 45), 1)
        cv2.putText(img, str(bpm_ref), (x0 + 4, yy - 3),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (90, 90, 90), 1)
    if len(hist) < 2:
        return
    vals = np.clip(np.array(hist, float), lo, hi)
    xs = np.linspace(0, len(vals) - 1, min(len(vals), w))
    vals = np.interp(xs, np.arange(len(vals)), vals)
    pts = [(x0 + int(i * w / len(vals)),
            int(y0 + h - (v - lo) / (hi - lo) * h)) for i, v in enumerate(vals)]
    for i in range(1, len(pts)):
        cv2.line(img, pts[i - 1], pts[i], cor, 2, cv2.LINE_AA)
    if pts:
        cv2.circle(img, pts[-1], 4, cor, -1, cv2.LINE_AA)


def painel_param(img, x0, y0, w, h, rotulo, valor, unidade, cor, sub=""):
    """Bloco de parâmetro: rótulo pequeno + valor grande + unidade."""
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), (35, 35, 35), -1)
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), (70, 70, 70), 1)
    cv2.putText(img, rotulo, (x0 + 10, y0 + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 1, cv2.LINE_AA)
    cv2.putText(img, valor, (x0 + 8, y0 + h - 18),
                cv2.FONT_HERSHEY_SIMPLEX, 1.6, cor, 3, cv2.LINE_AA)
    if unidade:
        cv2.putText(img, unidade, (x0 + w - 52, y0 + h - 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor, 1, cv2.LINE_AA)
    if sub:
        cv2.putText(img, sub, (x0 + 10, y0 + 40),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, C_TXT, 1, cv2.LINE_AA)


def monta_monitor(cam, sinal, bpm, snr, hrv, conf, ok_bpm, batida,
                  bpm_hist, gravando, relogio):
    """Compõe a tela completa estilo monitor de sinais vitais."""
    W, H = 1100, 620
    mon = np.full((H, W, 3), 16, dtype=np.uint8)  # fundo quase preto

    # ---- Barra superior ----
    cv2.rectangle(mon, (0, 0), (W, 34), (28, 28, 28), -1)
    cv2.putText(mon, "rPPG MONITOR  -  Pulso optico (POS)", (12, 23),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (220, 220, 220), 1, cv2.LINE_AA)
    cv2.putText(mon, relogio, (W - 360, 23),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, C_TXT, 1, cv2.LINE_AA)
    cv2.putText(mon, "ADULTO", (W - 210, 23),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, C_HR, 1, cv2.LINE_AA)
    cv2.putText(mon, "q=sair r=REC", (W - 130, 23),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, C_TXT, 1, cv2.LINE_AA)
    if gravando:
        cv2.circle(mon, (W - 145, 18), 6, C_ALARM, -1, cv2.LINE_AA)

    # ---- Câmera embutida (canto sup. esquerdo) ----
    cam_w, cam_h = 420, 315
    cam_r = cv2.resize(cam, (cam_w, cam_h))
    cx0, cy0 = 12, 44
    mon[cy0:cy0 + cam_h, cx0:cx0 + cam_w] = cam_r
    cv2.rectangle(mon, (cx0, cy0), (cx0 + cam_w, cy0 + cam_h), (70, 70, 70), 1)
    cv2.putText(mon, "CAM / ROI", (cx0 + 8, cy0 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (180, 180, 180), 1, cv2.LINE_AA)

    # ---- Traçado pulsátil (faixa direita superior) ----
    tx0, ty0, tw, th = 448, 44, W - 448 - 12, 200
    desenha_grade(mon, tx0, ty0, tw, th)
    cv2.rectangle(mon, (tx0, ty0), (tx0 + tw, ty0 + th), (70, 70, 70), 1)
    cor_tr = C_HR if ok_bpm else C_ALARM
    desenha_traçado(mon, sinal, tx0, ty0, tw, th, cor_tr, 0)
    cv2.putText(mon, "PLETH", (tx0 + 8, ty0 + 22),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, cor_tr, 1, cv2.LINE_AA)

    # ---- Tendência real de BPM no tempo (faixa inferior larga) ----
    bx0, by0, bw, bh = 448, 256, W - 448 - 12, 150
    cv2.rectangle(mon, (bx0, by0), (bx0 + bw, by0 + bh), (70, 70, 70), 1)
    desenha_tendencia(mon, bpm_hist, bx0, by0, bw, bh, (120, 200, 255))
    cv2.putText(mon, "TENDENCIA HR (bpm)", (bx0 + 8, by0 + 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (120, 200, 255), 1, cv2.LINE_AA)

    # ---- Painéis de parâmetros (linha inferior) ----
    py0 = 420
    pw, ph, gap = 250, 130, 12
    # HR com símbolo de coração que pulsa na batida
    valor_hr = f"{bpm:3.0f}" if ok_bpm else "--"
    painel_param(mon, 12, py0, pw, ph, "HR  bpm", valor_hr, "", C_HR,
                 sub="freq. cardiaca")
    r_cor = 9 if batida else 6
    cv2.circle(mon, (12 + pw - 34, py0 + 28), r_cor, C_HR, -1, cv2.LINE_AA)

    painel_param(mon, 12 + (pw + gap), py0, pw, ph, "SQI  %",
                 f"{conf*100:3.0f}", "", C_CONF, sub=f"SNR {snr:+.1f} dB")
    painel_param(mon, 12 + 2 * (pw + gap), py0, pw, ph, "HRV  ms",
                 f"{hrv:3.0f}" if hrv > 0 else "--", "", C_HRV, sub="SDNN")

    # bloco de estado/alarme
    sx0 = 12 + 3 * (pw + gap)
    sw = W - sx0 - 12
    cv2.rectangle(mon, (sx0, py0), (sx0 + sw, py0 + ph), (35, 35, 35), -1)
    cv2.rectangle(mon, (sx0, py0), (sx0 + sw, py0 + ph), (70, 70, 70), 1)
    if ok_bpm:
        cv2.putText(mon, "SINAL OK", (sx0 + 16, py0 + 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, C_HR, 2, cv2.LINE_AA)
        cv2.putText(mon, "monitorando", (sx0 + 16, py0 + 82),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, C_TXT, 1, cv2.LINE_AA)
    else:
        cv2.putText(mon, "! BUSCANDO", (sx0 + 16, py0 + 50),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, C_ALARM, 2, cv2.LINE_AA)
        cv2.putText(mon, "fique parado/iluminado", (sx0 + 16, py0 + 82),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (120, 120, 255), 1, cv2.LINE_AA)
    cv2.putText(mon, "demonstracao - nao e dispositivo medico",
                (sx0 + 16, py0 + ph - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.4, (110, 110, 110), 1, cv2.LINE_AA)
    return mon


def media_roi(frame, x, y, w, h):
    """Média RGB apenas sobre pixels de pele (máscara YCrCb).

    Descarta sobrancelha, sombra, cabelo e fundo dentro do retângulo,
    o que aumenta bastante o SNR do pulso.
    """
    h_img, w_img = frame.shape[:2]
    x, y = max(0, x), max(0, y)
    roi = frame[y:min(y + h, h_img), x:min(x + w, w_img)]
    if roi.size == 0:
        return None
    ycrcb = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    pele = roi[mask > 0]
    if len(pele) < 0.2 * (roi.shape[0] * roi.shape[1]):
        pele = roi.reshape(-1, 3)  # fallback: pouca pele detectada
    b, g, r = pele[:, 0].mean(), pele[:, 1].mean(), pele[:, 2].mean()
    return np.array([r, g, b])


def main():
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Erro: webcam indisponível.")
        return

    rgb_buf = deque(maxlen=N_MAX)
    t_buf = deque(maxlen=N_MAX)
    bpm_recent = deque(maxlen=7)       # estimativas brutas p/ mediana
    bpm_hist = deque(maxlen=300)       # tendência exibida
    bpm = snr = hrv = 0.0
    conf = 0.0
    sinal_plot = []
    ok_bpm = False
    ultima_batida = 0.0
    batida = False
    box = None                         # caixa do rosto suavizada (EMA)
    sem_rosto = 0
    gravando = False
    csv_writer = csv_file = None
    t0 = time.time()

    cv2.namedWindow("rPPG MONITOR", cv2.WINDOW_NORMAL)
    print("Mantenha o rosto iluminado e parado por ~8 s. 'q'=sair  'r'=grava CSV.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5, minSize=(120, 120))

        # rastreamento simples: suaviza a caixa e mantém quando perde detecção
        if len(faces):
            det = max(faces, key=lambda f: f[2] * f[3]).astype(float)
            box = det if box is None else 0.6 * box + 0.4 * det
            sem_rosto = 0
        else:
            sem_rosto += 1
            if sem_rosto > 30:
                box = None

        if box is not None:
            x, y, w, h = box.astype(int)
            cv2.rectangle(frame, (x, y), (x + w, y + h), (230, 180, 0), 1)

            # 3 ROIs de pele: testa, bochecha esq, bochecha dir
            rois = [
                (x + int(w * 0.30), y + int(h * 0.07), int(w * 0.40), int(h * 0.18)),
                (x + int(w * 0.12), y + int(h * 0.55), int(w * 0.22), int(h * 0.22)),
                (x + int(w * 0.66), y + int(h * 0.55), int(w * 0.22), int(h * 0.22)),
            ]
            medias = []
            for (rx, ry, rw, rh) in rois:
                cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (0, 220, 0), 1)
                m = media_roi(frame, rx, ry, rw, rh)
                if m is not None:
                    medias.append(m)
            if medias:
                rgb_buf.append(np.mean(medias, axis=0))
                t_buf.append(time.time() - t0)

        # Processa quando há janela suficiente
        if len(rgb_buf) >= int(FS_ALVO * 4):
            try:
                rgb_u, fs = reamostra_uniforme(t_buf, np.array(rgb_buf))
                pulso = banda(detrend(pos_algorithm(rgb_u, fs)), fs)
                bpm_inst, snr = bpm_e_snr(pulso, fs)
                hrv = calcula_hrv(pulso, fs)
                conf = float(np.clip((snr + 3) / 10.0, 0, 1))  # SNR~7dB -> 1.0
                sinal_plot = pulso
                if 40 <= bpm_inst <= 180 and conf >= 0.4:
                    bpm_recent.append(bpm_inst)
                if bpm_recent:
                    bpm = float(np.median(bpm_recent))  # suaviza p/ exibição
            except Exception:
                pass

        ok_bpm = 40 <= bpm <= 180 and conf >= 0.4 and len(bpm_recent) >= 2

        # "batida": pisca o coração no ritmo estimado do BPM
        agora = time.time()
        if ok_bpm and bpm > 0 and (agora - ultima_batida) >= (60.0 / bpm):
            ultima_batida = agora
            batida = True
        elif agora - ultima_batida > 0.12:
            batida = False

        # histórico de tendência (1 ponto por segundo aprox.)
        if ok_bpm and (not bpm_hist or agora - getattr(main, "_last_t", 0) >= 1.0):
            bpm_hist.append(bpm)
            main._last_t = agora

        # gravação CSV
        if gravando and csv_writer is not None:
            csv_writer.writerow([f"{agora - t0:.2f}", f"{bpm:.1f}",
                                 f"{snr:.2f}", f"{conf:.3f}", f"{hrv:.1f}"])

        relogio = time.strftime("%H:%M:%S")
        mon = monta_monitor(frame, sinal_plot, bpm, snr, hrv, conf, ok_bpm,
                            batida, bpm_hist, gravando, relogio)
        cv2.imshow("rPPG MONITOR", mon)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord("q"):
            break
        if tecla == ord("r"):
            gravando = not gravando
            if gravando:
                nome = time.strftime("rppg_%Y%m%d_%H%M%S.csv")
                csv_file = open(nome, "w", newline="")
                csv_writer = csv.writer(csv_file)
                csv_writer.writerow(["t_s", "bpm", "snr_db", "conf", "hrv_ms"])
                print(f"Gravando -> {nome}")
            elif csv_file:
                csv_file.close()
                print("Gravacao encerrada.")

    if csv_file:
        csv_file.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
