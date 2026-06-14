# 💓 Batimentos pela Pele — rPPG em Python

Mede a **frequência cardíaca pela webcam**, sem nenhum sensor de contato, detectando
a variação sutil da cor da pele a cada batimento (**fotopletismografia remota — rPPG**).

O **app desktop `vitalscan`** (PyQt6) implementa o algoritmo **POS**
(*Plane-Orthogonal-to-Skin*, Wang et al., IEEE TBME 2017) num ensemble com CHROM
e canal verde, exibindo os resultados numa interface no estilo de
**monitor de sinais vitais hospitalar**, com captura em thread dedicada,
gauge animado e gráficos em tempo real (pyqtgraph).

![monitor](docs/preview.png)

## Recursos

### Precisão & validação
- **Ensemble de algoritmos** — **POS** (Wang 2017) + **CHROM** (de Haan 2013) +
  canal verde, fundidos por peso de SNR.
- **Validação cruzada** — concordância entre os dois métodos de maior SNR.
- **Verificação independente** — HR por **autocorrelação** confrontado com a FFT.
- **Interpolação parabólica do pico** — precisão de BPM abaixo da resolução do bin.
- **Máscara de pele (YCrCb)** — média só sobre pixels de pele dentro das ROIs.
- **Múltiplas ROIs** — testa + duas bochechas, combinadas.
- **Reamostragem uniforme** — corrige a amostragem irregular da webcam antes da FFT.
- **Rejeição de movimento** — descarta frames com salto brusco da ROI.
- **Suavização com rejeição de outliers** — mediana temporal + rastreamento da face (EMA).
- **SQI composto** — combina SNR + concordância de métodos + concordância FFT/autocorr.

### App desktop (PyQt6)
- **Interface nativa** "VitalScan": cards arredondados, **gauge circular animado**
  da FC com coração pulsante em sincronia com a batida, barra de qualidade,
  gráfico de **tendência** e **pletismograma ao vivo** (pyqtgraph).
- **Captura em thread separada** (`QThread`) — a UI nunca trava.
- **Seleção de câmera** no cabeçalho + **status ao vivo** (sem rosto / calibrando /
  sinal OK / ajustando) e **FPS**.
- **Métricas exibidas** — BPM, SQI (%), HRV (SDNN, ms) e painel de validação cruzada.
- **Gravação CSV** com diálogo de salvar — grava `t, bpm, snr, sqi, hrv, bpm_autocorr`.
- **Atalhos** — `Espaço` inicia/para · `R` grava · `Q` fecha.

## Instalação

```bash
pip3 install -r requirements.txt
```

## Uso

### App desktop (recomendado)

```bash
python3 -m vitalscan
```

Escolha a câmera, clique **Iniciar** (ou `Espaço`) e mantenha o rosto bem iluminado
e relativamente parado por ~8 s para a leitura estabilizar.

## Arquitetura (`vitalscan/`)

| Módulo | Responsabilidade |
|---|---|
| `dsp.py` | Núcleo de sinal (POS/CHROM/verde, ensemble, SQI) — puro, sem UI |
| `worker.py` | `QThread` de captura + processamento; emite `Amostra` por frame |
| `widgets.py` | Widgets customizados (gauge, cards, plots, vídeo) |
| `main_window.py` | Janela principal, layout e controles |
| `theme.py` | Paleta e folha de estilo (QSS) |
| `cameras.py` | Enumeração de câmeras |
| `app.py` / `__main__.py` | Ponto de entrada |

## ⚠️ Aviso

Demonstração **educativa**. **Não é um dispositivo médico** e não deve ser usado
para diagnóstico ou decisões de saúde.

## Licença

MIT
