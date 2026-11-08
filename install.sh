#!/usr/bin/env bash
set -euo pipefail

APP_NAME="QuickClip"
SCRIPT_DIR="$(cd -P -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
INSTALL_DIR="${QUICKCLIP_INSTALL_DIR:-$DATA_HOME/quickclip}"
BIN_DIR="${QUICKCLIP_BIN_DIR:-$HOME/.local/bin}"
SKIP_DESKTOP="${QUICKCLIP_SKIP_DESKTOP:-0}"
INSTALL_DEPS=1
if [ "${QUICKCLIP_NO_INSTALL_DEPS:-0}" = "1" ]; then
    INSTALL_DEPS=0
fi
FORCE=0
PYTHON_BIN=""

usage() {
    cat <<EOF
Uso: ./install.sh [opciones]

Instala QuickClip en tu directorio de usuario. Si faltan dependencias,
ofrece instalarlas con el gestor de paquetes de tu distribución tras pedir
confirmación. No instala nada de forma silenciosa.

Opciones:
  --install-dir DIR   Copia la aplicación en DIR (por defecto $INSTALL_DIR)
  --bin-dir DIR       Crea el lanzador en DIR (por defecto $BIN_DIR)
  --no-desktop        No crea la entrada de menú ni el icono
  --no-install-deps   Solo comprueba dependencias; no ofrece instalarlas
  --force             Sobrescribe archivos de instalación no reconocidos
  -h, --help          Muestra esta ayuda

Variables de entorno equivalentes:
  QUICKCLIP_INSTALL_DIR, QUICKCLIP_BIN_DIR, QUICKCLIP_SKIP_DESKTOP=1,
  QUICKCLIP_NO_INSTALL_DEPS=1
EOF
}

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --install-dir)
            [ "$#" -ge 2 ] || die "--install-dir necesita una ruta"
            INSTALL_DIR="$2"
            shift 2
            ;;
        --bin-dir)
            [ "$#" -ge 2 ] || die "--bin-dir necesita una ruta"
            BIN_DIR="$2"
            shift 2
            ;;
        --no-desktop)
            SKIP_DESKTOP=1
            shift
            ;;
        --no-install-deps)
            INSTALL_DEPS=0
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
            die "opción desconocida: $1 (usa --help)"
            ;;
    esac
done

[ "$(uname -s)" = "Linux" ] || die "QuickClip solo está disponible para Linux."

case "$INSTALL_DIR" in
    ""|"/"|"$HOME"|"$HOME/") die "ruta de instalación no válida: $INSTALL_DIR" ;;
esac

[ -f "$SCRIPT_DIR/main.py" ] || die "no se encontró main.py. Ejecuta el instalador desde la raíz del repositorio."
[ -d "$SCRIPT_DIR/quickclip" ] || die "no se encontró el paquete quickclip."

MISSING=()
NEED_PYTHON=0
NEED_PYQT=0
NEED_FFMPEG=0
PM=""
PM_COMMAND=()
PYTHON_PACKAGE=""
PYQT_PACKAGE=""
SYS_PACKAGES=()
SYS_CMD=()
PIP_CMD=()
PRIV=()
DEPS_INSTALLED=0

detect_dependencies() {
    MISSING=()
    NEED_PYTHON=0
    NEED_PYQT=0
    NEED_FFMPEG=0
    PYTHON_BIN=""

    if ! command -v python3 >/dev/null 2>&1; then
        NEED_PYTHON=1
    else
        PYTHON_BIN="$(command -v python3)"
        if ! "$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' >/dev/null 2>&1; then
            NEED_PYTHON=1
            PYTHON_BIN=""
        fi
    fi

    if [ -z "$PYTHON_BIN" ] || ! "$PYTHON_BIN" -c 'import PyQt6' >/dev/null 2>&1; then
        NEED_PYQT=1
    fi
    if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
        NEED_FFMPEG=1
    fi

    if [ "$NEED_PYTHON" -eq 1 ]; then
        MISSING+=("Python 3.10+")
    fi
    if [ "$NEED_PYQT" -eq 1 ]; then
        MISSING+=("PyQt6")
    fi
    if [ "$NEED_FFMPEG" -eq 1 ]; then
        MISSING+=("FFmpeg/FFprobe")
    fi
}

manual_instructions() {
    cat <<'EOF'
Instala las dependencias manualmente:

  Ubuntu / Debian:  sudo apt install ffmpeg python3-pyqt6
  Fedora:           sudo dnf install ffmpeg python3-qt6
  Arch Linux:       sudo pacman -S ffmpeg python-pyqt6
  openSUSE:         sudo zypper install ffmpeg python3-PyQt6
  Alpine:           sudo apk add ffmpeg py3-pyqt6

También puedes usar un entorno virtual:
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt

Después vuelve a ejecutar ./install.sh.
EOF
}

detect_package_manager() {
    if command -v apt-get >/dev/null 2>&1; then
        PM="apt-get"
        PM_COMMAND=(apt-get install -y)
        PYTHON_PACKAGE="python3"
        PYQT_PACKAGE="python3-pyqt6"
    elif command -v dnf >/dev/null 2>&1; then
        PM="dnf"
        PM_COMMAND=(dnf install -y)
        PYTHON_PACKAGE="python3"
        PYQT_PACKAGE="python3-qt6"
    elif command -v pacman >/dev/null 2>&1; then
        PM="pacman"
        PM_COMMAND=(pacman -S --needed --noconfirm)
        PYTHON_PACKAGE="python"
        PYQT_PACKAGE="python-pyqt6"
    elif command -v zypper >/dev/null 2>&1; then
        PM="zypper"
        PM_COMMAND=(zypper --non-interactive install)
        PYTHON_PACKAGE="python3"
        PYQT_PACKAGE="python3-PyQt6"
    elif command -v apk >/dev/null 2>&1; then
        PM="apk"
        PM_COMMAND=(apk add --no-cache)
        PYTHON_PACKAGE="python3"
        PYQT_PACKAGE="py3-pyqt6"
    else
        PM=""
        PM_COMMAND=()
        PYTHON_PACKAGE=""
        PYQT_PACKAGE=""
    fi
}

add_package() {
    local package="$1"
    local existing
    for existing in "${SYS_PACKAGES[@]}"; do
        if [ "$existing" = "$package" ]; then
            return
        fi
    done
    SYS_PACKAGES+=("$package")
}

privilege_command() {
    PRIV=()
    if [ "$(id -u)" -eq 0 ]; then
        return 0
    fi
    if command -v sudo >/dev/null 2>&1; then
        PRIV=(sudo)
        return 0
    fi
    if command -v doas >/dev/null 2>&1; then
        PRIV=(doas)
        return 0
    fi
    return 1
}

build_dependency_plan() {
    local venv_active=0
    local need_pip=0
    local can_system=1

    if [ -n "${VIRTUAL_ENV:-}" ]; then
        venv_active=1
    fi

    detect_package_manager
    SYS_PACKAGES=()
    SYS_CMD=()
    PIP_CMD=()

    if [ "$NEED_FFMPEG" -eq 1 ]; then
        add_package "ffmpeg"
    fi
    if [ "$NEED_PYTHON" -eq 1 ]; then
        if [ -n "$PYTHON_PACKAGE" ]; then
            add_package "$PYTHON_PACKAGE"
        else
            can_system=0
        fi
    fi
    if [ "$NEED_PYQT" -eq 1 ]; then
        if [ "$venv_active" -eq 1 ] && [ -n "$PYTHON_BIN" ]; then
            need_pip=1
        elif [ -n "$PYQT_PACKAGE" ]; then
            add_package "$PYQT_PACKAGE"
        else
            can_system=0
        fi
    fi

    if [ "$can_system" -eq 0 ] && [ "${#SYS_PACKAGES[@]}" -gt 0 ]; then
        return 1
    fi
    if [ "${#SYS_PACKAGES[@]}" -gt 0 ] && [ -z "$PM" ]; then
        return 1
    fi
    if [ "${#SYS_PACKAGES[@]}" -gt 0 ]; then
        if ! privilege_command; then
            return 1
        fi
        if [ "${#PRIV[@]}" -gt 0 ]; then
            SYS_CMD=("${PRIV[@]}" "${PM_COMMAND[@]}" "${SYS_PACKAGES[@]}")
        else
            SYS_CMD=("${PM_COMMAND[@]}" "${SYS_PACKAGES[@]}")
        fi
    fi
    if [ "$need_pip" -eq 1 ]; then
        if ! "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
            return 1
        fi
        PIP_CMD=("$PYTHON_BIN" -m pip install -r "$SCRIPT_DIR/requirements.txt")
    fi
    if [ "${#SYS_CMD[@]}" -eq 0 ] && [ "${#PIP_CMD[@]}" -eq 0 ]; then
        return 1
    fi
    return 0
}

print_install_plan() {
    printf 'Faltan dependencias: %s\n' "${MISSING[*]}"
    if [ "${#SYS_CMD[@]}" -gt 0 ]; then
        printf '\nSe ejecutará:\n  '
        printf '%q ' "${SYS_CMD[@]}"
        printf '\n'
    fi
    if [ "${#PIP_CMD[@]}" -gt 0 ]; then
        printf '\nEn el entorno virtual se ejecutará:\n  '
        printf '%q ' "${PIP_CMD[@]}"
        printf '\n'
    fi
    printf '\n'
}

install_dependencies() {
    local answer

    if [ "$INSTALL_DEPS" -ne 1 ]; then
        print_install_plan >&2
        manual_instructions >&2
        exit 1
    fi
    if ! build_dependency_plan; then
        print_install_plan >&2
        printf 'No se pudo preparar la instalación automática para esta distribución.\n\n' >&2
        manual_instructions >&2
        exit 1
    fi
    if [ ! -t 0 ]; then
        print_install_plan >&2
        printf 'No hay una terminal interactiva para pedir confirmación.\n\n' >&2
        manual_instructions >&2
        exit 1
    fi

    print_install_plan
    printf '¿Instalarlas ahora? Se pedirá tu contraseña si hace falta. [s/N] '
    if ! read -r answer; then
        answer=""
    fi
    case "$answer" in
        s|S|si|sí|y|Y|yes|YES) ;;
        *)
            printf '\nInstalación cancelada.\n\n'
            manual_instructions >&2
            exit 1
            ;;
    esac

    if [ "${#SYS_CMD[@]}" -gt 0 ]; then
        printf '\nEjecutando: '
        printf '%q ' "${SYS_CMD[@]}"
        printf '\n'
        if ! "${SYS_CMD[@]}"; then
            printf '\nError: no se pudieron instalar los paquetes del sistema.\n\n' >&2
            manual_instructions >&2
            exit 1
        fi
        DEPS_INSTALLED=1
    fi
    if [ "${#PIP_CMD[@]}" -gt 0 ]; then
        printf '\nEjecutando: '
        printf '%q ' "${PIP_CMD[@]}"
        printf '\n'
        if ! "${PIP_CMD[@]}"; then
            printf '\nError: no se pudo instalar PyQt6 en el entorno virtual.\n\n' >&2
            manual_instructions >&2
            exit 1
        fi
        DEPS_INSTALLED=1
    fi

    detect_dependencies
    if [ "${#MISSING[@]}" -gt 0 ]; then
        printf '\nError: siguen faltando dependencias: %s\n\n' "${MISSING[*]}" >&2
        manual_instructions >&2
        exit 1
    fi
}

detect_dependencies
if [ "${#MISSING[@]}" -gt 0 ]; then
    install_dependencies
fi

if [ -e "$INSTALL_DIR" ] && [ ! -f "$INSTALL_DIR/.quickclip-install" ] && [ "$FORCE" -ne 1 ]; then
    die "$INSTALL_DIR ya existe y no parece una instalación de QuickClip. Usa --force para sobrescribir."
fi
if [ -e "$BIN_DIR/quickclip" ] && ! grep -q '^# QuickClip launcher$' "$BIN_DIR/quickclip" 2>/dev/null && [ "$FORCE" -ne 1 ]; then
    die "$BIN_DIR/quickclip ya existe y no pertenece a QuickClip. Usa --force para sobrescribir."
fi

DESKTOP_DIR="$DATA_HOME/applications"
ICON_DIR="$DATA_HOME/icons/hicolor/scalable/apps"
DESKTOP_FILE="$DESKTOP_DIR/quickclip.desktop"
ICON_FILE="$ICON_DIR/quickclip.svg"

if [ "$SKIP_DESKTOP" != "1" ]; then
    if [ -e "$DESKTOP_FILE" ] && ! grep -q '^X-QuickClip=true$' "$DESKTOP_FILE" 2>/dev/null && [ "$FORCE" -ne 1 ]; then
        die "$DESKTOP_FILE ya existe y no pertenece a QuickClip. Usa --force para sobrescribir."
    fi
    if [ -e "$ICON_FILE" ] && ! grep -q 'QuickClip icon' "$ICON_FILE" 2>/dev/null && [ "$FORCE" -ne 1 ]; then
        die "$ICON_FILE ya existe y no parece un icono de QuickClip. Usa --force para sobrescribir."
    fi
fi

APP_VERSION="$(sed -n 's/^APP_VERSION = "\(.*\)"/\1/p' "$SCRIPT_DIR/quickclip/config.py" | head -n 1)"
APP_VERSION="${APP_VERSION:-dev}"
STAGING="$INSTALL_DIR.new.$$"
trap 'rm -rf -- "$STAGING"' EXIT

mkdir -p -- "$(dirname -- "$INSTALL_DIR")" "$BIN_DIR"
rm -rf -- "$STAGING"
mkdir -p -- "$STAGING"
cp -- "$SCRIPT_DIR/main.py" "$SCRIPT_DIR/run.sh" "$SCRIPT_DIR/requirements.txt" \
    "$SCRIPT_DIR/README.md" "$SCRIPT_DIR/LICENSE" "$STAGING/"
cp -R -- "$SCRIPT_DIR/quickclip" "$STAGING/quickclip"
find "$STAGING" -type d -name __pycache__ -prune -exec rm -rf -- {} +
find "$STAGING" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
printf 'name=QuickClip\nversion=%s\nsource=%s\n' "$APP_VERSION" "$SCRIPT_DIR" > "$STAGING/.quickclip-install"

BACKUP=""
if [ -e "$INSTALL_DIR" ]; then
    BACKUP="$INSTALL_DIR.old.$$"
    mv -- "$INSTALL_DIR" "$BACKUP"
fi
if ! mv -- "$STAGING" "$INSTALL_DIR"; then
    if [ -n "$BACKUP" ]; then
        mv -- "$BACKUP" "$INSTALL_DIR"
    fi
    die "no se pudo mover la instalación a $INSTALL_DIR"
fi
if [ -n "$BACKUP" ]; then
    rm -rf -- "$BACKUP"
fi
trap - EXIT
chmod 0755 -- "$INSTALL_DIR/run.sh"

printf -v QUOTED_PYTHON '%q' "$PYTHON_BIN"
printf -v QUOTED_MAIN '%q' "$INSTALL_DIR/main.py"
cat > "$BIN_DIR/quickclip" <<EOF
#!/usr/bin/env bash
# QuickClip launcher
set -euo pipefail
export QT_LOGGING_RULES="\${QT_LOGGING_RULES:-qt.qpa.wayland.textinput=false}"
PYTHON_BIN=$QUOTED_PYTHON
if [ ! -x "\$PYTHON_BIN" ]; then
    PYTHON_BIN=python3
fi
if ! command -v ffmpeg >/dev/null 2>&1 || ! command -v ffprobe >/dev/null 2>&1; then
    echo "QuickClip necesita FFmpeg y FFprobe. Instálalos con tu gestor de paquetes." >&2
    exit 1
fi
if ! command -v "\$PYTHON_BIN" >/dev/null 2>&1 || ! "\$PYTHON_BIN" -c 'import PyQt6' >/dev/null 2>&1; then
    echo "QuickClip necesita Python 3.10+ y PyQt6. Instálalos con tu gestor de paquetes." >&2
    exit 1
fi
exec "\$PYTHON_BIN" $QUOTED_MAIN "\$@"
EOF
chmod 0755 -- "$BIN_DIR/quickclip"

if [ "$SKIP_DESKTOP" != "1" ]; then
    mkdir -p -- "$DESKTOP_DIR" "$ICON_DIR"
    cp -- "$SCRIPT_DIR/quickclip/assets/quickclip.svg" "$ICON_FILE"

    ESCAPED_LAUNCHER="$BIN_DIR/quickclip"
    ESCAPED_LAUNCHER="${ESCAPED_LAUNCHER//\\/\\\\}"
    ESCAPED_LAUNCHER="${ESCAPED_LAUNCHER//\"/\\\"}"
    ESCAPED_LAUNCHER="${ESCAPED_LAUNCHER//\$/\\$}"
    ESCAPED_LAUNCHER="${ESCAPED_LAUNCHER//\`/\\\`}"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=QuickClip
GenericName=Editor de clips
Comment=Editor rápido de clips para Linux
Exec="$ESCAPED_LAUNCHER" %F
Icon=quickclip
Terminal=false
Categories=AudioVideo;Video;
MimeType=video/mp4;video/x-matroska;video/quicktime;video/webm;video/x-msvideo;
StartupNotify=true
X-QuickClip=true
EOF
    chmod 0644 -- "$DESKTOP_FILE"

    command -v update-desktop-database >/dev/null 2>&1 && update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true
    if command -v gtk-update-icon-cache >/dev/null 2>&1 && [ -f "$DATA_HOME/icons/hicolor/index.theme" ]; then
        gtk-update-icon-cache -q -t -f "$DATA_HOME/icons/hicolor" >/dev/null 2>&1 || true
    fi
fi

printf '\nQuickClip %s instalado correctamente.\n' "$APP_VERSION"
printf '  Aplicación: %s\n' "$INSTALL_DIR"
printf '  Lanzador:   %s\n' "$BIN_DIR/quickclip"
if [ "$SKIP_DESKTOP" != "1" ]; then
    printf '  Menú:       %s\n' "$DESKTOP_FILE"
fi
if [ "$DEPS_INSTALLED" -eq 1 ]; then
    printf '\nDependencias instaladas con tu confirmación.\n'
else
    printf '\nNo se modificaron dependencias del sistema.\n'
fi

case ":${PATH:-}:" in
    *":$BIN_DIR:"*) ;;
    *)
        printf '\nAñade %s a tu PATH para ejecutar "quickclip" desde cualquier terminal:\n' "$BIN_DIR"
        printf '  export PATH="%s:$PATH"\n' "$BIN_DIR"
        ;;
esac
printf 'Puedes abrirlo desde el menú de aplicaciones o ejecutando: quickclip\n'
