#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

export QT_LOGGING_RULES="${QT_LOGGING_RULES:-qt.qpa.wayland.textinput=false}"

if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    echo "QuickClip necesita FFmpeg y FFprobe. Instálalos con:" >&2
    echo "    sudo apt install ffmpeg" >&2
    exit 1
fi

if ! python3 -c "import PyQt6" >/dev/null 2>&1; then
    echo "QuickClip necesita PyQt6. Instálalo con:" >&2
    echo "    sudo apt install python3-pyqt6" >&2
    echo "o dentro de un entorno virtual: pip install -r requirements.txt" >&2
    exit 1
fi

exec python3 "$SCRIPT_DIR/main.py" "$@"
