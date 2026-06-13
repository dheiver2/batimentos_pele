# 💓 Batimentos pela Pele — rPPG em Python

Mede a **frequência cardíaca pela webcam**, sem nenhum sensor de contato, detectando
a variação sutil da cor da pele a cada batimento (**fotopletismografia remota — rPPG**).

A versão principal (`rppg_pos.py`) implementa o algoritmo **POS**
(*Plane-Orthogonal-to-Skin*, Wang et al., IEEE TBME 2017) e exibe os resultados
numa interface no estilo de **monitor de sinais vitais hospitalar**.

![monitor](docs/preview.png)

## Recursos

- **Algoritmo POS** — projeta o RGB num plano ortogonal ao tom de pele, cancelando
  ruído de movimento e iluminação (muito mais robusto que a média do canal verde).
- **Máscara de pele (YCrCb)** — média apenas sobre pixels de pele dentro das ROIs.
- **Múltiplas ROIs** — testa + duas bochechas, combinadas.
- **Reamostragem uniforme** — corrige a amostragem irregular da webcam antes da FFT.
- **Suavização** — mediana das estimativas recentes + rastreamento da face (EMA).
- **Métricas** — BPM, qualidade do sinal (SQI via SNR em dB) e HRV (SDNN).
- **Interface tipo monitor** — traçado PLETH sobre grade de ECG, tendência de BPM,
  coração que pisca no ritmo, relógio e alarme de sinal.
- **Gravação CSV** — tecla `r` grava `t, bpm, snr, conf, hrv` para análise posterior.

## Instalação

```bash
pip3 install -r requirements.txt
```

## Uso

```bash
python3 rppg_pos.py        # versão científica + monitor médico
python3 batimentos_pele.py # versão simples (canal verde) p/ comparação
```

Teclas: **`q`** sai · **`r`** liga/desliga a gravação CSV.

Mantenha o rosto bem iluminado e relativamente parado por ~8 s para a leitura estabilizar.

## Arquivos

| Arquivo | Descrição |
|---|---|
| `rppg_pos.py` | Versão principal: POS + monitor médico |
| `batimentos_pele.py` | Versão simples (média do canal verde) |
| `roteiro_reels.md` | Roteiro de vídeo (Reels/TikTok) do projeto |
| `requirements.txt` | Dependências |

## ⚠️ Aviso

Demonstração **educativa**. **Não é um dispositivo médico** e não deve ser usado
para diagnóstico ou decisões de saúde.

## Licença

MIT
