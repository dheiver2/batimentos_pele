"""Paleta e folha de estilo (QSS) do VitalScan — minimalista, black."""

# Preto puro com elevações quase imperceptíveis
BG = "#000000"
PANEL = "#080808"        # elevação 1 (quase invisível)
PANEL_HI = "#111111"     # elevação 2 (hover / trilhos)
LINE = "#1c1c1c"         # hairline
TXT = "#f5f5f5"
MUT = "#666666"          # texto secundário discreto
FAINT = "#3a3a3a"        # rótulos micro

# Acento único — verde clínico, usado só para dado vivo
ACC = "#5cf08a"
ACC_DIM = "#1e3a28"
WARN = "#ff5a4d"
ACC_B = "#f5f5f5"        # SQI agora monocromático (white)
ACC_P = "#9a9a9a"        # HRV monocromático (cinza)

QSS = f"""
* {{
    font-family: -apple-system, "SF Pro Display", "Segoe UI", "Inter", sans-serif;
    color: {TXT};
}}
QMainWindow, QWidget#root {{
    background: {BG};
}}

/* Painéis sem moldura — separação por espaço, não por borda */
QFrame#card {{
    background: transparent;
    border: none;
}}

QLabel#cardTitle {{
    color: {FAINT};
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2.5px;
}}
QLabel#brand {{
    font-size: 20px;
    font-weight: 800;
    letter-spacing: 4px;
}}
QLabel#brandSub {{
    color: {MUT};
    font-size: 10px;
    letter-spacing: 1px;
}}
QLabel#metricBig {{
    font-size: 34px;
    font-weight: 300;
}}
QLabel#metricUnit {{
    color: {MUT};
    font-size: 12px;
    font-weight: 400;
}}
QLabel#footer {{
    color: {FAINT};
    font-size: 10px;
    letter-spacing: 0.5px;
}}

/* Botões fantasma — texto + hairline, sem preenchimento */
QPushButton {{
    background: transparent;
    border: 1px solid {LINE};
    border-radius: 999px;
    padding: 9px 22px;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.5px;
    color: {TXT};
}}
QPushButton:hover {{ background: {PANEL_HI}; border-color: {MUT}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {LINE}; }}
QPushButton#primary {{
    background: {ACC};
    color: #032512;
    border: none;
    font-weight: 700;
}}
QPushButton#primary:hover {{ background: #7bf8a4; }}
QPushButton#danger {{
    background: transparent;
    color: {WARN};
    border: 1px solid {WARN};
}}
QPushButton#danger:hover {{ background: rgba(255,90,77,0.10); }}

QComboBox {{
    background: transparent;
    border: 1px solid {LINE};
    border-radius: 999px;
    padding: 8px 16px;
    font-size: 12px;
    color: {MUT};
    min-width: 130px;
}}
QComboBox:hover {{ border-color: {MUT}; color: {TXT}; }}
QComboBox QAbstractItemView {{
    background: #0c0c0c;
    border: 1px solid {LINE};
    selection-background-color: {PANEL_HI};
    outline: none;
    padding: 4px;
}}
QComboBox::drop-down {{ border: none; width: 20px; }}
QToolTip {{
    background: #0c0c0c;
    color: {TXT};
    border: 1px solid {LINE};
    padding: 6px;
}}
"""
