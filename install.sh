#!/usr/bin/env bash
#
# install.sh - one-shot YTVoice setup (LFS pull + deps + verify + smoke test)
#
# Works on Linux, macOS, Windows (git-bash), and Termux/Android (PRoot or host).
# Run this AFTER cloning, from inside the repo:
#
#   git clone https://github.com/acadiemedia/ytvoice.git
#   cd ytvoice
#   ./install.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

EXPECTED_BIN_SIZE=238736226
PYTHON="${PYTHON:-python3}"

log()  { printf '\033[1;32m[*]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[!!]\033[0m %b\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Git LFS
# ---------------------------------------------------------------------------
log "Checking Git LFS..."
if ! command -v git-lfs >/dev/null 2>&1; then
    warn "git-lfs is not installed. Install it, then re-run this script:"
    case "$(uname -s)" in
        Linux)  warn "  Debian/Ubuntu: sudo apt install git-lfs" ;;
        Darwin) warn "  brew install git-lfs" ;;
        *)      warn "  Termux: pkg install git-lfs" ;;
    esac
    warn "Until git-lfs is installed, binary-database mode cannot work."
    exit 1
fi

if ! git lfs version >/dev/null 2>&1; then
    warn "git-lfs binary found but the git lfs command failed."
    warn "Add it to your PATH, then re-run: git lfs install && git lfs pull"
    exit 1
fi

log "Initializing Git LFS hooks..."
git lfs install >/dev/null 2>&1 || true

# ---------------------------------------------------------------------------
# 2. Verify the sprite database is the real file, not a pointer
# ---------------------------------------------------------------------------
log "Verifying voice database..."
BIN_SIZE=0
if [ -f voice_sprites.bin ]; then
    if stat -c %s voice_sprites.bin >/dev/null 2>&1; then
        BIN_SIZE=$(stat -c %s voice_sprites.bin)
    else
        BIN_SIZE=$(stat -f %z voice_sprites.bin)
    fi
fi

if [ -n "$BIN_SIZE" ] && [ "$BIN_SIZE" -ge 1000000 ]; then
    log "voice_sprites.bin already present ($BIN_SIZE bytes); skipping LFS download."
else
    log "Pulling LFS objects (~238 MB, one-time download)..."
    git lfs pull || true
fi

# Re-check size after any pull attempt
if [ -f voice_sprites.bin ]; then
    if stat -c %s voice_sprites.bin >/dev/null 2>&1; then
        BIN_SIZE=$(stat -c %s voice_sprites.bin)
    else
        BIN_SIZE=$(stat -f %z voice_sprites.bin)
    fi
fi
if [ -z "$BIN_SIZE" ] || [ "$BIN_SIZE" -lt 1000000 ]; then
    die "voice_sprites.bin is still only ${BIN_SIZE:-0} bytes (LFS pull did not download it).\n   Check network, then re-run: git lfs pull && ./install.sh"
fi
log "voice_sprites.bin OK ($BIN_SIZE bytes)"

# ---------------------------------------------------------------------------
# 3. Python dependencies (PEP 668 aware)
# ---------------------------------------------------------------------------
log "Installing Python dependencies..."
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    die "python3 not found. Install Python first (Termux: pkg install python)."
fi

EXTERNAL=$("$PYTHON" -c "
import sysconfig, os, glob
roots = set(sysconfig.get_paths().values())
found = any(os.path.exists(os.path.join(r, 'EXTERNALLY-MANAGED'))
            or glob.glob(os.path.join(r, '**', 'EXTERNALLY-MANAGED'), recursive=True)
            for r in roots)
print(bool(found))
" 2>/dev/null || echo False)

PIP_OPTS=()
if [ "$EXTERNAL" = "True" ]; then
    warn "Externally-managed environment detected (PEP 668). Using --break-system-packages."
    PIP_OPTS+=(--break-system-packages)
fi

"$PYTHON" -m pip install "${PIP_OPTS[@]:-}" -r requirements.txt

# ---------------------------------------------------------------------------
# 4. Smoke test
# ---------------------------------------------------------------------------
log "Smoke test (offline binary-database mode)..."
"$PYTHON" src/player.py "hello this works" --no-play --bin voice_sprites.bin

log "Install complete. Run it now with:  $PYTHON src/player.py \"hello steve\""