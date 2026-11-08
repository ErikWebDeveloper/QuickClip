#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
CACHE_HOME="${XDG_CACHE_HOME:-$HOME/.cache}"
INSTALL_DIR="${QUICKCLIP_INSTALL_DIR:-$DATA_HOME/quickclip}"
BIN_DIR="${QUICKCLIP_BIN_DIR:-$HOME/.local/bin}"
DESKTOP_FILE="$DATA_HOME/applications/quickclip.desktop"
ICON_FILE="$DATA_HOME/icons/hicolor/scalable/apps/quickclip.svg"
PURGE=0
FORCE=0
ERRORS=0

usage() {
    cat <<EOF
Uso: ./uninstall.sh [opciones]

Desinstala QuickClip del directorio de usuario. No usa sudo y no elimina
dependencias del sistema ni tus videos.

Opciones:
  --install-dir DIR   Directorio donde se instaló la aplicación
  --bin-dir DIR       Directorio donde está el lanzador
  --purge             Elimina también la caché y la configuración de QuickClip
  --force             Elimina archivos aunque no tengan la marca de QuickClip
  -h, --help          Muestra esta ayuda

Variables de entorno equivalentes:
  QUICKCLIP_INSTALL_DIR, QUICKCLIP_BIN_DIR
EOF
}

warn() {
    printf 'Aviso: %s\n' "$*" >&2
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --install-dir)
            [ "$#" -ge 2 ] || { warn "--install-dir necesita una ruta"; exit 1; }
            INSTALL_DIR="$2"
            shift 2
            ;;
        --bin-dir)
            [ "$#" -ge 2 ] || { warn "--bin-dir necesita una ruta"; exit 1; }
            BIN_DIR="$2"
            shift 2
            ;;
        --purge)
            PURGE=1
            shift
            ;;
        --force)
            FORCE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            warn "opción desconocida: $1 (usa --help)"
            exit 1
            ;;
    esac
done

[ "$(uname -s)" = "Linux" ] || { warn "QuickClip solo está disponible para Linux."; exit 1; }

case "$INSTALL_DIR" in
    ""|"/"|"$HOME"|"$HOME/") warn "ruta de instalación no válida: $INSTALL_DIR"; exit 1 ;;
esac

remove_launcher() {
    local launcher="$BIN_DIR/quickclip"
    if [ ! -e "$launcher" ]; then
        return
    fi
    if grep -q '^# QuickClip launcher$' "$launcher" 2>/dev/null || [ "$FORCE" -eq 1 ]; then
        rm -f -- "$launcher"
        printf 'Eliminado: %s\n' "$launcher"
    else
        warn "$launcher no parece de QuickClip; se conserva (usa --force para eliminarlo)."
        ERRORS=1
    fi
}

remove_desktop() {
    if [ ! -e "$DESKTOP_FILE" ]; then
        return
    fi
    if grep -q '^X-QuickClip=true$' "$DESKTOP_FILE" 2>/dev/null || [ "$FORCE" -eq 1 ]; then
        rm -f -- "$DESKTOP_FILE"
        printf 'Eliminado: %s\n' "$DESKTOP_FILE"
    else
        warn "$DESKTOP_FILE no parece de QuickClip; se conserva (usa --force para eliminarlo)."
        ERRORS=1
    fi
}

remove_icon() {
    if [ ! -e "$ICON_FILE" ]; then
        return
    fi
    if grep -q 'QuickClip icon' "$ICON_FILE" 2>/dev/null || [ "$FORCE" -eq 1 ]; then
        rm -f -- "$ICON_FILE"
        printf 'Eliminado: %s\n' "$ICON_FILE"
    else
        warn "$ICON_FILE no parece de QuickClip; se conserva (usa --force para eliminarlo)."
        ERRORS=1
    fi
}

remove_launcher
remove_desktop
remove_icon

if [ -d "$INSTALL_DIR" ]; then
    if [ -f "$INSTALL_DIR/.quickclip-install" ] || [ "$FORCE" -eq 1 ]; then
        rm -rf -- "$INSTALL_DIR"
        printf 'Eliminado: %s\n' "$INSTALL_DIR"
    else
        warn "$INSTALL_DIR no parece de QuickClip; se conserva (usa --force para eliminarlo)."
        ERRORS=1
    fi
elif [ -e "$INSTALL_DIR" ]; then
    warn "$INSTALL_DIR no es un directorio; se conserva."
    ERRORS=1
fi

if [ "$PURGE" -eq 1 ]; then
    CACHE_DIR="$CACHE_HOME/quickclip"
    CONFIG_DIR="$CONFIG_HOME/QuickClip"
    if [ -d "$CACHE_DIR" ]; then
        rm -rf -- "$CACHE_DIR"
        printf 'Eliminado: %s\n' "$CACHE_DIR"
    fi
    if [ -d "$CONFIG_DIR" ]; then
        rm -rf -- "$CONFIG_DIR"
        printf 'Eliminado: %s\n' "$CONFIG_DIR"
    fi
    printf 'También se eliminaron la caché y la configuración de QuickClip.\n'
else
    printf 'Se conservaron la caché y la configuración. Usa --purge para eliminarlas.\n'
fi

command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DATA_HOME/applications" >/dev/null 2>&1 || true
if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ -f "$DATA_HOME/icons/hicolor/index.theme" ]; then
    gtk-update-icon-cache -q -t -f "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
fi

printf '\nQuickClip desinstalado. No se eliminaron dependencias ni archivos de video.\n'
exit "$ERRORS"
