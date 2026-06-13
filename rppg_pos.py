"""
rPPG PRO — frequência cardíaca pela webcam, com ensemble de algoritmos,
validação cruzada e interface comercial.

Técnicas de precisão:
  - Ensemble POS (Wang 2017) + CHROM (de Haan 2013) + canal verde,
    fundidos por peso de SNR.
  - Validação cruzada entre métodos (concordância POS<->CHROM).
  - Verificação independente por autocorrelação (método diferente da FFT).
  - Interpolação parabólica do pico espectral (precisão sub-bin).
  - Reamostragem uniforme (corrige amostragem irregular da webcam).
  - Rejeição de artefato de movimento + suavização com rejeição de outliers.
  - SQI composto (SNR + concordância + proeminência do pico).

Requisitos:  pip3 install opencv-python numpy scipy
Uso:         python3 rppg_pos.py        ('q' = sair, 'r' = grava CSV)

Aviso: demonstração educativa. Não é dispositivo médico.
"""

import csv
import time
from collections import deque

import cv2
import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

# ----- Parâmetros -----
JANELA_SEG = 8
FS_ALVO = 30.0
FREQ_MIN, FREQ_MAX = 0.7, 3.0        # Hz -> 42 a 180 bpm
N_MAX = int(JANELA_SEG * 60)


# ============================ Núcleo de sinal ============================

def reamostra_uniforme(t, y, fs=FS_ALVO):
    """Interpola sinais multicanal num grid temporal uniforme."""
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
    n = len(x)
    t = np.arange(n)
    a, b = np.polyfit(t, x, 1)
    return x - (a * t + b)


def banda(x, fs, low=FREQ_MIN, high=FREQ_MAX, ordem=4):
    nyq = 0.5 * fs
    lo, hi = max(low / nyq, 1e-3), min(high / nyq, 0.99)
    b, a = butter(ordem, [lo, hi], btype="band")
    return filtfilt(b, a, x)


def _normaliza(rgb):
    """RGB (N,3) -> (3,N) normalizado pela média temporal de cada canal."""
    C = rgb.T.astype(float)
    mu = np.mean(C, axis=1, keepdims=True)
    mu[mu == 0] = 1e-8
    return C / mu


def pulso_pos(rgb, fs):
    """POS (Plane-Orthogonal-to-Skin, Wang 2017)."""
    Cn = _normaliza(rgb)
    S1 = Cn[1] - Cn[2]
    S2 = Cn[1] + Cn[2] - 2 * Cn[0]
    s2s = np.std(S2)
    alpha = np.std(S1) / s2s if s2s > 1e-8 else 0.0
    return banda(detrend(S1 + alpha * S2), fs)


def pulso_chrom(rgb, fs):
    """CHROM (de Haan & Jeanne 2013)."""
    Cn = _normaliza(rgb)
    X = 3 * Cn[0] - 2 * Cn[1]
    Y = 1.5 * Cn[0] + Cn[1] - 1.5 * Cn[2]
    Xf = banda(detrend(X), fs)
    Yf = banda(detrend(Y), fs)
    s = np.std(Yf)
    alpha = np.std(Xf) / s if s > 1e-8 else 0.0
    return Xf - alpha * Yf


def pulso_verde(rgb, fs):
    """Canal verde simples (linha de base)."""
    return banda(detrend(rgb[:, 1].astype(float)), fs)


def _interp_parabolica(p, i):
    """Refina índice do pico por interpolação parabólica (sub-bin)."""
    if 0 < i < len(p) - 1:
        a, b, c = p[i - 1], p[i], p[i + 1]
        denom = (a - 2 * b + c)
        if abs(denom) > 1e-12:
            return i + 0.5 * (a - c) / denom
    return float(i)


def bpm_e_snr(sinal, fs):
    """(bpm, snr_db, proeminencia) via FFT com zero-pad e refino sub-bin."""
    s = (sinal - np.mean(sinal)) * np.hanning(len(sinal))
    nfft = int(2 ** np.ceil(np.log2(len(s) * 8)))
    psd = np.abs(np.fft.rfft(s, n=nfft)) ** 2
    freqs = np.fft.rfftfreq(nfft, 1.0 / fs)
    mask = (freqs >= FREQ_MIN) & (freqs <= FREQ_MAX)
    if not np.any(mask):
        return 0.0, -99.0, 0.0
    f_band, p_band = freqs[mask], psd[mask]
    i_pico = int(np.argmax(p_band))
    df = freqs[1] - freqs[0]
    f_pico = (f_band[0] + _interp_parabolica(p_band, i_pico) * df)
    bpm = f_pico * 60.0
    # SNR: energia perto do pico (+1º harmônico) vs. resto da banda
    sig_mask = np.zeros_like(p_band, dtype=bool)
    for fc in (f_pico, 2 * f_pico):
        sig_mask |= np.abs(f_band - fc) <= 0.15
    sig_p = np.sum(p_band[sig_mask])
    noise_p = np.sum(p_band[~sig_mask]) + 1e-12
    snr_db = 10 * np.log10(sig_p / noise_p)
    # proeminência: pico / mediana da banda
    prom = float(p_band[i_pico] / (np.median(p_band) + 1e-12))
    return bpm, snr_db, prom


def hr_autocorrelacao(sinal, fs):
    """HR independente via autocorrelação (verificação cruzada com a FFT)."""
    s = sinal - np.mean(sinal)
    ac = np.correlate(s, s, mode="full")[len(s) - 1:]
    lo = int(fs / FREQ_MAX)
    hi = int(fs / FREQ_MIN)
    if hi <= lo + 1 or hi >= len(ac):
        return 0.0
    seg = ac[lo:hi]
    lag = lo + int(np.argmax(seg))
    return 60.0 * fs / lag if lag > 0 else 0.0


def calcula_hrv(sinal, fs):
    """SDNN (ms) a partir dos intervalos entre picos."""
    s = (sinal - np.mean(sinal)) / (np.std(sinal) + 1e-8)
    dist = int(fs * 0.4)
    picos, _ = find_peaks(s, distance=max(dist, 1), prominence=0.3)
    if len(picos) < 3:
        return 0.0
    rr = np.diff(picos) / fs * 1000.0
    return float(np.std(rr))


def estima_ensemble(rgb_u, fs):
    """
    Roda os 3 métodos, funde por SNR e calcula validação cruzada.
    Retorna dict com bpm, snr, sqi, hrv, sinal de melhor método e diagnósticos.
    """
    metodos = {
        "POS": pulso_pos(rgb_u, fs),
        "CHROM": pulso_chrom(rgb_u, fs),
        "GREEN": pulso_verde(rgb_u, fs),
    }
    est = {}
    for nome, sig in metodos.items():
        bpm, snr, prom = bpm_e_snr(sig, fs)
        est[nome] = {"bpm": bpm, "snr": snr, "prom": prom, "sig": sig}

    # fusão ponderada por SNR positivo (softmax suave)
    pesos = {k: max(v["snr"], 0.0) + 1e-3 for k, v in est.items()}
    wsum = sum(pesos.values())
    bpm_fus = sum(est[k]["bpm"] * pesos[k] for k in est) / wsum

    # ranking por SNR; melhor método guia traçado / HRV / autocorrelação
    rank = sorted(est, key=lambda k: est[k]["snr"], reverse=True)
    melhor = rank[0]
    segundo = rank[1]
    sig_melhor = est[melhor]["sig"]
    snr_melhor = est[melhor]["snr"]
    bpm_ac = hr_autocorrelacao(sig_melhor, fs)
    hrv = calcula_hrv(sig_melhor, fs)

    # ---- Validação cruzada / SQI composto ----
    # 1) concordância entre os DOIS métodos de maior SNR (não compara lixo)
    dif_metodos = abs(est[melhor]["bpm"] - est[segundo]["bpm"])
    acordo_met = float(np.clip(1 - dif_metodos / 12.0, 0, 1))
    # 2) concordância FFT (fusão) <-> autocorrelação (método independente)
    dif_ac = abs(bpm_fus - bpm_ac) if bpm_ac > 0 else 12.0
    acordo_ac = float(np.clip(1 - dif_ac / 12.0, 0, 1))
    # 3) SNR normalizado
    sqi_snr = float(np.clip((snr_melhor + 3) / 10.0, 0, 1))
    # 4) proeminência do pico
    sqi_prom = float(np.clip((est[melhor]["prom"] - 2) / 10.0, 0, 1))
    sqi = 0.40 * sqi_snr + 0.30 * acordo_met + 0.20 * acordo_ac + 0.10 * sqi_prom

    return {
        "bpm": bpm_fus, "bpm_ac": bpm_ac, "snr": snr_melhor, "hrv": hrv,
        "sqi": float(sqi), "melhor": melhor, "segundo": segundo,
        "sig": sig_melhor,
        "bpm_m1": est[melhor]["bpm"], "bpm_m2": est[segundo]["bpm"],
        "acordo_met": acordo_met, "acordo_ac": acordo_ac,
    }


def media_roi(frame, x, y, w, h):
    """Média RGB apenas sobre pixels de pele (máscara YCrCb)."""
    h_img, w_img = frame.shape[:2]
    x, y = max(0, x), max(0, y)
    roi = frame[y:min(y + h, h_img), x:min(x + w, w_img)]
    if roi.size == 0:
        return None
    ycrcb = cv2.cvtColor(roi, cv2.COLOR_BGR2YCrCb)
    mask = cv2.inRange(ycrcb, (0, 133, 77), (255, 173, 127))
    pele = roi[mask > 0]
    if len(pele) < 0.2 * (roi.shape[0] * roi.shape[1]):
        pele = roi.reshape(-1, 3)
    b, g, r = pele[:, 0].mean(), pele[:, 1].mean(), pele[:, 2].mean()
    return np.array([r, g, b])


# ====================== UI comercial (dashboard) ======================

BG = (20, 16, 13)
CARD = (34, 28, 23)
CARD_HI = (46, 39, 32)
LINE = (62, 54, 46)
ACC = (150, 230, 130)        # verde-menta  (HR)
ACC_B = (235, 195, 95)       # azul-ciano   (SQI)
ACC_P = (210, 140, 200)      # roxo         (HRV)
WARN = (70, 95, 240)         # vermelho-laranja (alarme)
TXT = (235, 235, 235)
MUT = (135, 130, 125)
GRID = (44, 58, 44)


def card(img, x, y, w, h, fill=CARD, r=16, topo=None):
    """Cartão de cantos arredondados; faixa de acento opcional no topo."""
    cv2.rectangle(img, (x + r, y), (x + w - r, y + h), fill, -1)
    cv2.rectangle(img, (x, y + r), (x + w, y + h - r), fill, -1)
    for cx, cy in [(x + r, y + r), (x + w - r, y + r),
                   (x + r, y + h - r), (x + w - r, y + h - r)]:
        cv2.circle(img, (cx, cy), r, fill, -1)
    if topo is not None:
        cv2.rectangle(img, (x + r, y), (x + w - r, y + 4), topo, -1)


def txt(img, s, x, y, scale=0.5, cor=TXT, th=1, font=cv2.FONT_HERSHEY_SIMPLEX):
    cv2.putText(img, s, (x, y), font, scale, cor, th, cv2.LINE_AA)


def barra(img, x, y, w, h, frac, cor):
    cv2.rectangle(img, (x, y), (x + w, y + h), CARD_HI, -1)
    fw = int(w * float(np.clip(frac, 0, 1)))
    if fw > 0:
        cv2.rectangle(img, (x, y), (x + fw, y + h), cor, -1)


def heart(img, cx, cy, s, cor):
    """Coração simples (dois círculos + triângulo)."""
    r = max(2, int(s * 0.5))
    cv2.circle(img, (cx - r // 1, cy), r, cor, -1, cv2.LINE_AA)
    cv2.circle(img, (cx + r // 1, cy), r, cor, -1, cv2.LINE_AA)
    pts = np.array([[cx - 2 * r, cy + 1], [cx + 2 * r, cy + 1],
                    [cx, cy + 2 * r + 2]], np.int32)
    cv2.fillPoly(img, [pts], cor, cv2.LINE_AA)


def ring(img, cx, cy, raio, frac, cor, esp=10):
    cv2.ellipse(img, (cx, cy), (raio, raio), 0, 0, 360, CARD_HI, esp)
    ang = int(360 * float(np.clip(frac, 0, 1)))
    cv2.ellipse(img, (cx, cy), (raio, raio), -90, 0, ang, cor, esp,
                cv2.LINE_AA)


def grade(img, x, y, w, h, passo=22):
    for i, gx in enumerate(range(x, x + w, passo)):
        cv2.line(img, (gx, y), (gx, y + h), GRID, 1)
    for j, gy in enumerate(range(y, y + h, passo)):
        cv2.line(img, (x, gy), (x + w, gy), GRID, 1)


def traçado(img, sinal, x, y, w, h, cor):
    if len(sinal) < 2:
        return
    s = np.array(sinal, float)
    s = s - s.mean()
    amp = np.max(np.abs(s)) or 1.0
    s = s / amp
    xs = np.linspace(0, len(s) - 1, w)
    s = np.interp(xs, np.arange(len(s)), s)
    cy = y + h // 2
    pts = [(x + i, int(cy - v * h * 0.42)) for i, v in enumerate(s)]
    for i in range(1, len(pts)):
        cv2.line(img, pts[i - 1], pts[i], cor, 2, cv2.LINE_AA)
    if pts:
        cv2.circle(img, pts[-1], 3, cor, -1, cv2.LINE_AA)


def sparkline(img, hist, x, y, w, h, cor, lo=45, hi=150):
    if len(hist) < 2:
        return
    v = np.clip(np.array(hist, float), lo, hi)
    xs = np.linspace(0, len(v) - 1, min(len(v), w))
    v = np.interp(xs, np.arange(len(v)), v)
    pts = [(x + int(i * w / len(v)), int(y + h - (val - lo) / (hi - lo) * h))
           for i, val in enumerate(v)]
    for i in range(1, len(pts)):
        cv2.line(img, pts[i - 1], pts[i], cor, 2, cv2.LINE_AA)


def dashboard(cam, R, bpm, sqi, ok, batida, hist, gravando, relogio):
    """Monta a interface comercial completa."""
    W, H = 1280, 720
    img = np.full((H, W, 3), BG, np.uint8)

    # ---- Header ----
    txt(img, "VITALSCAN", 28, 40, 0.95, TXT, 2)
    txt(img, "rPPG  -  monitor de pulso optico", 215, 40, 0.5, MUT, 1)
    dot = ACC if ok else WARN
    cv2.circle(img, (W - 340, 33), 6, dot, -1, cv2.LINE_AA)
    txt(img, "SINAL OK" if ok else "AJUSTANDO", W - 325, 38, 0.5, dot, 1)
    if gravando:
        cv2.circle(img, (W - 190, 33), 6, WARN, -1, cv2.LINE_AA)
        txt(img, "REC", W - 178, 38, 0.45, WARN, 1)
    txt(img, relogio, W - 110, 38, 0.6, TXT, 1)

    # ---- Webcam ----
    cx0, cy0, cw, ch = 28, 64, 430, 323
    card(img, cx0, cy0, cw, ch)
    cam_r = cv2.resize(cam, (cw - 16, ch - 40))
    img[cy0 + 32:cy0 + 32 + cam_r.shape[0], cx0 + 8:cx0 + 8 + cam_r.shape[1]] = cam_r
    txt(img, "CAMERA / ROI", cx0 + 16, cy0 + 24, 0.5, MUT, 1)

    # ---- HR hero ----
    hx, hy, hw, hh = 474, 64, 372, 323
    card(img, hx, hy, hw, hh, topo=ACC)
    txt(img, "FREQUENCIA CARDIACA", hx + 20, hy + 30, 0.5, MUT, 1)
    gx, gy = hx + 95, hy + 150
    ring(img, gx, gy, 78, (bpm - 40) / 140.0 if ok else 0, ACC, 11)
    valor = f"{bpm:.0f}" if ok else "--"
    (tw, _), _ = cv2.getTextSize(valor, cv2.FONT_HERSHEY_SIMPLEX, 1.9, 3)
    txt(img, valor, gx - tw // 2, gy + 14, 1.9, ACC if ok else MUT, 3)
    txt(img, "bpm", gx - 18, gy + 46, 0.5, MUT, 1)
    heart(img, hx + 250, hy + 70, 16 if batida else 12, ACC if ok else MUT)
    # sparkline de tendência
    txt(img, "tendencia", hx + 200, hy + 130, 0.42, MUT, 1)
    sparkline(img, hist, hx + 200, hy + 140, 150, 150, ACC)

    # ---- Coluna direita: SQI / HRV / Validação ----
    rx, rw = 866, 386
    chh, gap = 94, 20
    # SQI
    sy = 64
    card(img, rx, sy, rw, chh, topo=ACC_B)
    txt(img, "QUALIDADE DO SINAL (SQI)", rx + 18, sy + 26, 0.48, MUT, 1)
    txt(img, f"{sqi*100:.0f}%", rx + 18, sy + 68, 1.1, ACC_B, 2)
    barra(img, rx + 150, sy + 50, rw - 175, 14, sqi, ACC_B)
    # HRV
    hy2 = sy + chh + gap
    card(img, rx, hy2, rw, chh, topo=ACC_P)
    txt(img, "VARIABILIDADE (HRV / SDNN)", rx + 18, hy2 + 26, 0.48, MUT, 1)
    txt(img, f"{R['hrv']:.0f}" if ok and R['hrv'] > 0 else "--",
        rx + 18, hy2 + 70, 1.1, ACC_P, 2)
    txt(img, "ms", rx + 120, hy2 + 70, 0.5, MUT, 1)
    # Validação cruzada
    vy = hy2 + chh + gap
    card(img, rx, vy, rw, chh, topo=ACC)
    txt(img, "VALIDACAO CRUZADA", rx + 18, vy + 26, 0.48, MUT, 1)
    txt(img, f"{R['melhor']} {R['bpm_m1']:.0f}", rx + 18, vy + 60, 0.55, TXT, 1)
    txt(img, f"{R['segundo']} {R['bpm_m2']:.0f}", rx + 140, vy + 60, 0.55, TXT, 1)
    confirma = R['acordo_met'] >= 0.6 and R['acordo_ac'] >= 0.5
    sel = ACC if confirma else WARN
    txt(img, "CONFIRMADO" if confirma else "DIVERGENTE",
        rx + 268, vy + 60, 0.5, sel, 1)
    txt(img, "concordancia metodos / FFT~autocorr", rx + 18, vy + 82, 0.4, MUT, 1)
    txt(img, f"{R['acordo_met']*100:.0f}% / {R['acordo_ac']*100:.0f}%",
        rx + 268, vy + 82, 0.42, MUT, 1)

    # ---- PLETH (largura total) ----
    px, py, pw, ph = 28, 408, W - 56, 270
    card(img, px, py, pw, ph)
    txt(img, "PLETISMOGRAMA  (pulso optico)", px + 18, py + 28, 0.5, MUT, 1)
    gx0, gy0 = px + 16, py + 44
    gw0, gh0 = pw - 32, ph - 64
    grade(img, gx0, gy0, gw0, gh0)
    traçado(img, R['sig'], gx0, gy0, gw0, gh0, ACC if ok else WARN)

    txt(img, "Demonstracao educativa - nao e dispositivo medico.",
        28, H - 14, 0.42, MUT, 1)
    txt(img, "q = sair    r = gravar CSV", W - 250, H - 14, 0.42, MUT, 1)
    return img


# ============================== Loop principal ==============================

def main():
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("Erro: webcam indisponível.")
        return

    rgb_buf = deque(maxlen=N_MAX)
    t_buf = deque(maxlen=N_MAX)
    bpm_recent = deque(maxlen=7)
    bpm_hist = deque(maxlen=300)
    R = {"hrv": 0.0, "sig": [], "melhor": "-", "segundo": "-",
         "bpm_m1": 0, "bpm_m2": 0, "snr": 0.0,
         "acordo_met": 0.0, "acordo_ac": 0.0, "bpm_ac": 0.0}
    bpm = sqi = 0.0
    ok_bpm = False
    ultima_batida = 0.0
    batida = False
    box = None
    sem_rosto = 0
    verde_ant = None
    gravando = False
    csv_writer = csv_file = None
    t0 = time.time()
    main._last_t = 0.0

    cv2.namedWindow("VitalScan", cv2.WINDOW_NORMAL)
    print("Mantenha o rosto iluminado e parado por ~8 s. 'q'=sair  'r'=CSV.")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frame = cv2.flip(frame, 1)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = face_cascade.detectMultiScale(gray, 1.3, 5, minSize=(120, 120))

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
            cv2.rectangle(frame, (x, y), (x + w, y + h), (200, 160, 70), 1)
            rois = [
                (x + int(w * 0.30), y + int(h * 0.07), int(w * 0.40), int(h * 0.18)),
                (x + int(w * 0.12), y + int(h * 0.55), int(w * 0.22), int(h * 0.22)),
                (x + int(w * 0.66), y + int(h * 0.55), int(w * 0.22), int(h * 0.22)),
            ]
            medias = []
            for (rx, ry, rw, rh) in rois:
                cv2.rectangle(frame, (rx, ry), (rx + rw, ry + rh), (130, 220, 150), 1)
                m = media_roi(frame, rx, ry, rw, rh)
                if m is not None:
                    medias.append(m)
            if medias:
                rgb = np.mean(medias, axis=0)
                # rejeição de artefato de movimento (salto brusco no verde)
                if verde_ant is None or abs(rgb[1] - verde_ant) < 8.0:
                    rgb_buf.append(rgb)
                    t_buf.append(time.time() - t0)
                verde_ant = rgb[1]

        if len(rgb_buf) >= int(FS_ALVO * 4):
            try:
                rgb_u, fs = reamostra_uniforme(t_buf, np.array(rgb_buf))
                R = estima_ensemble(rgb_u, fs)
                sqi = R["sqi"]
                bpm_inst = R["bpm"]
                if 40 <= bpm_inst <= 180 and sqi >= 0.4:
                    # rejeita outlier vs. mediana atual
                    if not bpm_recent or abs(bpm_inst - np.median(bpm_recent)) < 15:
                        bpm_recent.append(bpm_inst)
                if bpm_recent:
                    bpm = float(np.median(bpm_recent))
            except Exception:
                pass

        ok_bpm = 40 <= bpm <= 180 and sqi >= 0.4 and len(bpm_recent) >= 2

        agora = time.time()
        if ok_bpm and bpm > 0 and (agora - ultima_batida) >= (60.0 / bpm):
            ultima_batida = agora
            batida = True
        elif agora - ultima_batida > 0.12:
            batida = False

        if ok_bpm and (not bpm_hist or agora - main._last_t >= 1.0):
            bpm_hist.append(bpm)
            main._last_t = agora

        if gravando and csv_writer is not None:
            csv_writer.writerow([f"{agora - t0:.2f}", f"{bpm:.1f}",
                                 f"{R['snr']:.2f}", f"{sqi:.3f}",
                                 f"{R['hrv']:.1f}", f"{R['bpm_ac']:.1f}"])

        relogio = time.strftime("%H:%M:%S")
        img = dashboard(frame, R, bpm, sqi, ok_bpm, batida, bpm_hist,
                        gravando, relogio)
        cv2.imshow("VitalScan", img)

        tecla = cv2.waitKey(1) & 0xFF
        if tecla == ord("q"):
            break
        if tecla == ord("r"):
            gravando = not gravando
            if gravando:
                nome = time.strftime("rppg_%Y%m%d_%H%M%S.csv")
                csv_file = open(nome, "w", newline="")
                csv_writer = csv.writer(csv_file)
                csv_writer.writerow(["t_s", "bpm", "snr_db", "sqi",
                                     "hrv_ms", "bpm_autocorr"])
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
