#!/bin/bash
# Cria o VitalScan.app (bundle macOS com ícone) que executa "python3 -m vitalscan".
#
# Uso:   bash scripts/build_app.sh [destino]
#        destino padrão: ~/Desktop
#
# Requer: python3 com as dependências de requirements.txt e o ícone em
#         assets/VitalScan.icns (gere com: python3 scripts/make_icon.py).

set -e
PROJ="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/Desktop}"
APP="$DEST/VitalScan.app"
ICNS="$PROJ/assets/VitalScan.icns"

[ -f "$ICNS" ] || python3 "$PROJ/scripts/make_icon.py"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$ICNS" "$APP/Contents/Resources/AppIcon.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>VitalScan</string>
  <key>CFBundleDisplayName</key><string>VitalScan</string>
  <key>CFBundleIdentifier</key><string>ai.mangaba.vitalscan</string>
  <key>CFBundleVersion</key><string>2.0.0</string>
  <key>CFBundleShortVersionString</key><string>2.0.0</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>vitalscan</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSCameraUsageDescription</key><string>O VitalScan usa a câmera para medir a frequência cardíaca por rPPG.</string>
</dict>
</plist>
PLIST

cat > "$APP/Contents/MacOS/vitalscan" <<SH
#!/bin/bash
cd "$PROJ" || exit 1
PY=\$(command -v python3)
NEED=0
"\$PY" - <<'PYCHK' 2>/dev/null || NEED=1
import importlib.util as u, sys
m=["PyQt6","cv2","numpy","scipy","pyqtgraph","mediapipe"]
sys.exit(0 if all(u.find_spec(x) for x in m) else 1)
PYCHK
if [ "\$NEED" = "1" ]; then
  /usr/bin/osascript -e 'display notification "Instalando dependências…" with title "VitalScan"'
  "\$PY" -m pip install -q -r requirements.txt
fi
exec "\$PY" -m vitalscan
SH
chmod +x "$APP/Contents/MacOS/vitalscan"
touch "$APP"

LSREG="/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister"
[ -x "$LSREG" ] && "$LSREG" -f "$APP" 2>/dev/null || true

echo "Criado: $APP"
