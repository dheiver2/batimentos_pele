"""
Núcleo de processamento de sinal rPPG.

Técnicas de precisão (idênticas à versão de referência):
  - Ensemble POS (Wang 2017) + CHROM (de Haan 2013) + canal verde,
    fundidos por peso de SNR.
  - Validação cruzada entre métodos (concordância POS<->CHROM).
  - Verificação independente por autocorrelação.
  - Interpolação parabólica do pico espectral (precisão sub-bin).
  - Reamostragem uniforme (corrige amostragem irregular da webcam).
  - SQI composto (SNR + concordância + proeminência do pico).

Este módulo é puro (sem dependências de UI): recebe RGB/tempo e devolve dados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
from scipy.signal import butter, filtfilt, find_peaks

# ----- Parâmetros globais -----
FS_ALVO = 30.0
FREQ_MIN, FREQ_MAX = 0.7, 3.0        # Hz -> 42 a 180 bpm
BPM_MIN, BPM_MAX = 40.0, 180.0


# ============================ Estrutura de resultado ============================

@dataclass
class Estimativa:
    """Resultado de uma estimativa de frequência cardíaca."""
    bpm: float = 0.0
    bpm_ac: float = 0.0
    snr: float = 0.0
    hrv: float = 0.0
    sqi: float = 0.0
    melhor: str = "-"
    segundo: str = "-"
    bpm_m1: float = 0.0
    bpm_m2: float = 0.0
    acordo_met: float = 0.0
    acordo_ac: float = 0.0
    sig: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def confirmado(self) -> bool:
        return self.acordo_met >= 0.6 and self.acordo_ac >= 0.5


# ============================ Funções de sinal ============================

def reamostra_uniforme(t, y, fs: float = FS_ALVO):
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
    sig_mask = np.zeros_like(p_band, dtype=bool)
    for fc in (f_pico, 2 * f_pico):
        sig_mask |= np.abs(f_band - fc) <= 0.15
    sig_p = np.sum(p_band[sig_mask])
    noise_p = np.sum(p_band[~sig_mask]) + 1e-12
    snr_db = 10 * np.log10(sig_p / noise_p)
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


def estima_ensemble(rgb_u, fs) -> Estimativa:
    """Roda os 3 métodos, funde por SNR e calcula validação cruzada."""
    metodos = {
        "POS": pulso_pos(rgb_u, fs),
        "CHROM": pulso_chrom(rgb_u, fs),
        "GREEN": pulso_verde(rgb_u, fs),
    }
    est: Dict[str, dict] = {}
    for nome, sig in metodos.items():
        bpm, snr, prom = bpm_e_snr(sig, fs)
        est[nome] = {"bpm": bpm, "snr": snr, "prom": prom, "sig": sig}

    pesos = {k: max(v["snr"], 0.0) + 1e-3 for k, v in est.items()}
    wsum = sum(pesos.values())
    bpm_fus = sum(est[k]["bpm"] * pesos[k] for k in est) / wsum

    rank = sorted(est, key=lambda k: est[k]["snr"], reverse=True)
    melhor, segundo = rank[0], rank[1]
    sig_melhor = est[melhor]["sig"]
    snr_melhor = est[melhor]["snr"]
    bpm_ac = hr_autocorrelacao(sig_melhor, fs)
    hrv = calcula_hrv(sig_melhor, fs)

    dif_metodos = abs(est[melhor]["bpm"] - est[segundo]["bpm"])
    acordo_met = float(np.clip(1 - dif_metodos / 12.0, 0, 1))
    dif_ac = abs(bpm_fus - bpm_ac) if bpm_ac > 0 else 12.0
    acordo_ac = float(np.clip(1 - dif_ac / 12.0, 0, 1))
    sqi_snr = float(np.clip((snr_melhor + 3) / 10.0, 0, 1))
    sqi_prom = float(np.clip((est[melhor]["prom"] - 2) / 10.0, 0, 1))
    sqi = 0.40 * sqi_snr + 0.30 * acordo_met + 0.20 * acordo_ac + 0.10 * sqi_prom

    return Estimativa(
        bpm=bpm_fus, bpm_ac=bpm_ac, snr=snr_melhor, hrv=hrv, sqi=float(sqi),
        melhor=melhor, segundo=segundo,
        bpm_m1=est[melhor]["bpm"], bpm_m2=est[segundo]["bpm"],
        acordo_met=acordo_met, acordo_ac=acordo_ac, sig=sig_melhor,
    )


def media_roi(frame, x, y, w, h):
    """Média RGB apenas sobre pixels de pele (máscara YCrCb)."""
    import cv2
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
