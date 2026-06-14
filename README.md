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
- **Ensemble de 5 algoritmos** — **POS** (Wang 2017, versão canônica com janela
  deslizante + *overlap-add*) + **CHROM** (de Haan 2013) + **LGI** (Pilz 2018) +
  **OMIT** (Álvarez-Casado & Bordallo-López 2023) + canal verde, fundidos por
  peso de SNR. POS, LGI e OMIT são os métodos não-supervisionados de melhor
  desempenho nos benchmarks rPPG-Toolbox (NeurIPS 2023) e pyVHR.
- **Validação cruzada** — concordância entre os dois métodos de maior SNR.
- **Verificação independente** — HR por **autocorrelação** confrontado com a FFT.
- **Interpolação parabólica do pico** — precisão de BPM abaixo da resolução do bin.
- **Face landmarks de alta precisão** — MediaPipe Face Mesh (478 pontos 3D)
  define ROIs de pele que acompanham o rosto pixel a pixel; *fallback*
  automático para detector Haar se o MediaPipe não estiver disponível.
- **Máscara de pele (YCrCb)** — média só sobre pixels de pele dentro das ROIs.
- **Múltiplas ROIs** — testa + duas bochechas, recortadas pelos landmarks.
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
| `landmarks.py` | Face Mesh (478 landmarks) → ROIs de pele precisas; fallback Haar |
| `widgets.py` | Widgets customizados (gauge, cards, plots, vídeo) |
| `main_window.py` | Janela principal, layout e controles |
| `theme.py` | Paleta e folha de estilo (QSS) |
| `cameras.py` | Enumeração de câmeras |
| `app.py` / `__main__.py` | Ponto de entrada |

## Referências

- Wang, W. et al. *Algorithmic Principles of Remote PPG (POS)*. IEEE TBME, 2017.
- de Haan, G. & Jeanne, V. *Robust Pulse Rate from Chrominance-Based rPPG (CHROM)*.
  IEEE TBME, 2013.
- Pilz, C. S. et al. *Local Group Invariance for Heart Rate Estimation from Face
  Videos (LGI)*. CVPRW, 2018.
- Álvarez-Casado, C. & Bordallo-López, M. *Face2PPG (OMIT)*. IEEE JBHI, 2023.
- Liu, X. et al. *rPPG-Toolbox: Deep Remote PPG Toolbox*. NeurIPS 2023.
- Boccignone, G. et al. *pyVHR: a Python framework for remote photoplethysmography*.
  PeerJ CS, 2022.

## ⚠️ Aviso

Demonstração **educativa**. **Não é um dispositivo médico** e não deve ser usado
para diagnóstico ou decisões de saúde.

## Licença

MIT
