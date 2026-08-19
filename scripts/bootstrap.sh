#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="python3"
VENV_PATH=".venv"
INSTALL_DEV=0
INSTALL_SCIENCE=0

usage() {
  cat <<'USAGE'
Usage: ./scripts/bootstrap.sh [options]

Options:
  --python PATH   Python interpreter to use, default: python3
  --venv PATH     Virtual environment path, default: .venv
  --dev           Install development and test dependencies
  --science       Install science dependencies, including PyArrow and SALib
  -h, --help      Show this help
USAGE
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --venv)
      VENV_PATH="$2"
      shift 2
      ;;
    --dev)
      INSTALL_DEV=1
      shift
      ;;
    --science)
      INSTALL_SCIENCE=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  exit 2
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11 or later is required, found {sys.version.split()[0]}")
print(f"Using Python {sys.version.split()[0]}")
PY

"$PYTHON_BIN" -m venv "$VENV_PATH"

if [[ -x "$VENV_PATH/bin/python" ]]; then
  VENV_PYTHON="$VENV_PATH/bin/python"
elif [[ -x "$VENV_PATH/Scripts/python.exe" ]]; then
  VENV_PYTHON="$VENV_PATH/Scripts/python.exe"
else
  echo "Virtual environment Python was not created correctly" >&2
  exit 2
fi

"$VENV_PYTHON" -m pip install --upgrade pip setuptools wheel

EXTRAS=()
if [[ "$INSTALL_DEV" -eq 1 ]]; then
  EXTRAS+=(dev)
fi
if [[ "$INSTALL_SCIENCE" -eq 1 ]]; then
  EXTRAS+=(science)
fi

if [[ ${#EXTRAS[@]} -eq 0 ]]; then
  INSTALL_TARGET="."
else
  IFS=,
  INSTALL_TARGET=".[${EXTRAS[*]}]"
  unset IFS
fi

"$VENV_PYTHON" -m pip install -e "$INSTALL_TARGET"

cat <<EOF2

Bootstrap complete.
Activate the environment with:
  source "$VENV_PATH/bin/activate"

Then verify the installation with:
  python scripts/verify_local_install.py --tests --demo
EOF2
