"""Paleta e folha de estilo (QSS) do VitalScan — tema escuro profissional."""

# Cores (hex) — coerentes com a identidade do dashboard original
BG = "#0e0c0b"
PANEL = "#1a1612"
PANEL_HI = "#241e18"
LINE = "#3a322c"
TXT = "#ececec"
MUT = "#8a847d"

ACC = "#96e682"        # verde-menta  (HR)
ACC_B = "#ebc35f"      # âmbar        (SQI)
ACC_P = "#d28cc8"      # roxo         (HRV)
WARN = "#f05f46"       # vermelho     (alarme)

QSS = f"""
* {{
    font-family: -apple-system, "SF Pro Display", "Segoe UI", "Inter", sans-serif;
    color: {TXT};
}}
QMainWindow, QWidget#root {{
    background: {BG};
}}
QFrame#card {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 16px;
}}
QLabel#cardTitle {{
    color: {MUT};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 1px;
}}
QLabel#brand {{
    font-size: 22px;
    font-weight: 800;
    letter-spacing: 2px;
}}
QLabel#brandSub {{
    color: {MUT};
    font-size: 11px;
}}
QLabel#metricBig {{
    font-size: 30px;
    font-weight: 800;
}}
QLabel#metricUnit {{
    color: {MUT};
    font-size: 12px;
}}
QLabel#footer {{
    color: {MUT};
    font-size: 11px;
}}
QPushButton {{
    background: {PANEL_HI};
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 9px 18px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{ background: {LINE}; }}
QPushButton:disabled {{ color: {MUT}; background: {PANEL}; }}
QPushButton#primary {{
    background: {ACC};
    color: #0c1a0c;
    border: none;
}}
QPushButton#primary:hover {{ background: #aef096; }}
QPushButton#danger {{
    background: {WARN};
    color: #240a06;
    border: none;
}}
QPushButton#danger:hover {{ background: #ff7359; }}
QComboBox {{
    background: {PANEL_HI};
    border: 1px solid {LINE};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
    min-width: 150px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL_HI};
    border: 1px solid {LINE};
    selection-background-color: {LINE};
    outline: none;
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QToolTip {{
    background: {PANEL_HI};
    color: {TXT};
    border: 1px solid {LINE};
    padding: 6px;
}}
"""
