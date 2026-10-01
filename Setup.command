#!/bin/bash
# =============================================================================
#  OfflineYT  -  one-shot macOS setup
#  ----------------------------------------------------------------------------
#  Double-click this file. It checks what you have, installs everything
#  OfflineYT needs (Homebrew, Python, yt-dlp, ffmpeg, aria2, rclone),
#  copies the yosync engine into place, and creates a sane starting config
#  + library folder — no manual steps.
#
#  Safe to run twice: it skips whatever is already installed.
#  Preview without changing anything:   SETUP_DRY_RUN=1 ./Setup.command
#  Requirements: macOS, internet access, an admin-capable account.
# =============================================================================
set -euo pipefail

BOLD=$'\033[1m'; DIM=$'\033[2m'; RESET=$'\033[0m'
ok()   { printf '%s %s%s\n' "${BOLD}✓${RESET}" "$1" "$RESET"; }
info() { printf '%s ▸ %s%s\n' "$DIM" "$1" "$RESET"; }

die() { printf '\n%s %s\n\n' "ERROR:" "$1" >&2; exit 1; }

[[ "$(uname -s)" == "Darwin" ]] || die "Setup.command is macOS-only. On Linux/Windows just run:  python3 bin/yosync"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
YOSYNC_SRC="$SCRIPT_DIR/bin/yosync"
CONFIG_EXAMPLE="$SCRIPT_DIR/config.example.json"
BIN_DIR="$HOME/bin"
YOSYNC_DST="$BIN_DIR/yosync"
CONFIG_DIR="$HOME/.config/yosync"
CONFIG_FILE="$CONFIG_DIR/config.json"
LIB_DIR="$HOME/Movies/OfflineYouTube"

DRY="${SETUP_DRY_RUN:-0}"
run() {
  if [[ "$DRY" == "1" ]]; then
    printf '%s[dry-run] %s%s\n' "$DIM" "$*" "$RESET"
  else
    "$@"
  fi
}

ask() {
  local q="$1" dflt="$2"
  [[ -t 0 ]] || { printf '%s' "$dflt"; return; }
  local ans
  read -r -p "$q" ans
  printf '%s' "${ans:-$dflt}"
}

printf '\n%s OfflineYT — automated setup %s\n\n' "$BOLD" "$RESET"

if [[ "$DRY" == "1" ]]; then
  printf '%s Preview mode — nothing will be changed.\n\n' "$DIM"
fi

# --- 1. Command Line Tools ------------------------------------------------
if xcode-select -p >/dev/null 2>&1; then
  ok "Xcode Command Line Tools"
else
  printf '%s Xcode Command Line Tools missing — opening the installer.\n' "$BOLD"
  echo "   Finish it, then come back and press Enter."
  run xcode-select --install
  read -r -p "   Press Enter after Xcode CLT is installed... " _
  xcode-select -p >/dev/null 2>&1 || die "Xcode CLT still missing. Run this file again after installing."
fi

# --- 2. Homebrew -----------------------------------------------------------
BREW=""
if command -v brew >/dev/null 2>&1; then
  BREW="$(command -v brew)"
  ok "Homebrew"
else
  printf '%s Homebrew missing — installing it (this can take a few minutes).\n' "$BOLD"
  run /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  BREW="$( [[ "$(uname -m)" == "arm64" ]] && echo /opt/homebrew/bin/brew || echo /usr/local/bin/brew )"
  [[ -x "$BREW" ]] || die "Homebrew install failed. Run the file again to retry."
  ok "Homebrew"
fi
export PATH="/opt/homebrew/bin:/usr/local/bin:$(dirname "$BREW"):$PATH"

# --- 3. Core packages -------------------------------------------------------
BASE=(git python@3.12 yt-dlp ffmpeg)
extra=$(ask "   Install aria2 (faster downloads) + rclone (Google Drive pull)? [Y/n] " "y")
if [[ "${extra:0:1}" =~ [Yy] ]]; then
  BASE+=(aria2 rclone)
  info "adding aria2 + rclone"
fi
info "brew install ${BASE[*]}"
run brew install "${BASE[@]}"

# --- 4. Pick a Python >= 3.10 ----------------------------------------------
PYBIN="$(command -v python3.12 || true)"
[[ -n "$PYBIN" ]] || PYBIN="$(command -v python3 || true)"
[[ -n "$PYBIN" ]] || die "No Python found. Install it:  brew install python@3.12"
if ! "$PYBIN" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
  printf '%s Python too old (%s) — install 3.10+ :  brew install python@3.12\n' "$BOLD" "$( "$PYBIN" -V 2>&1 )"
  die "Aborting."
fi
ok "Python $( "$PYBIN" -V 2>&1 | cut -d' ' -f2 )"

# --- 5. Library folder ------------------------------------------------------
info "creating library at $LIB_DIR"
run mkdir -p "$LIB_DIR/inbox" "$LIB_DIR/.yosync/incoming" "$LIB_DIR/.yosync/takeout" "$LIB_DIR/.yosync/logs"
ok "library folders"

# --- 6. Config (never overwrite an existing one) -----------------------------
mkdir -p "$CONFIG_DIR"
if [[ -f "$CONFIG_FILE" ]]; then
  ok "config already exists — kept as-is ($CONFIG_FILE)"
else
  [[ -f "$CONFIG_EXAMPLE" ]] || die "config.example.json is missing next to this file."
  if [[ "$DRY" == "1" ]]; then
    printf '%s[dry-run] generate %s%s\n' "$DIM" "$CONFIG_FILE" "$RESET"
  else
    "$PYBIN" - "$CONFIG_EXAMPLE" "$CONFIG_FILE" "$LIB_DIR" <<'PY'
import json, os, sys
_, example, target, lib = sys.argv
cfg = json.load(open(example))
cfg["dest"] = lib
cfg["daemon"] = False
with open(target, "w") as f:
    json.dump(cfg, f, indent=2)
print("    wrote", target)
PY
    ok "minimal config ($CONFIG_FILE)"
  fi
fi

# --- 7. yosync engine --------------------------------------------------------
[[ -f "$YOSYNC_SRC" ]] || die "bin/yosync not found next to this file — keep the repo folder together."
run mkdir -p "$BIN_DIR"
run cp "$YOSYNC_SRC" "$YOSYNC_DST"
run chmod +x "$YOSYNC_DST"
ok "yosync -> $YOSYNC_DST"

# --- 8. PATH so `yosync` works in your terminal ------------------------------
if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
  rc="$HOME/.zshrc"
  if [[ -f "$rc" ]] && grep -qF "export PATH=\"$BIN_DIR\$PATH\"" "$rc" 2>/dev/null; then
    :
  else
    a=$(ask "   Add ~/bin to your PATH in $rc? [Y/n] " "y")
    if [[ "${a:0:1}" =~ [Yy] ]]; then
      run bash -c "printf '\n# added by OfflineYT setup\nexport PATH=\"%s:\$PATH\"\n' \"$BIN_DIR\" >> \"$rc\""
      info "run \`source ~/.zshrc\` (or reopen Terminal) after this finishes"
    fi
  fi
fi

# --- 9. Quick sanity check ----------------------------------------------------
v=$(ask "   Run a quick self-check now (downloads nothing)? [Y/n] " "y")
if [[ "${v:0:1}" =~ [Yy] ]]; then
  info "yosync --help"
  run "$PYBIN" "$YOSYNC_DST" --help 2>&1 | head -n 15 || true
fi

# --- 10. Optional background daemon -------------------------------------------
d=$(ask "   Enable the daily 6am background sync (launchd)? [y/N] " "n")
if [[ "${d:0:1}" =~ [Yy] ]]; then
  run "$PYBIN" "$YOSYNC_DST" --daemon
  ok "6am daemon enabled (undo: yosync --no-daemon)"
fi

# --- done ---------------------------------------------------------------------
printf '\n%s Setup complete.%s\n\n' "$BOLD" "$RESET"
echo "  Next:"
echo "    1. Export your YouTube watch history from Google Takeout"
echo "       (youtube.com -> youtube music -> Watch history, JSON, monthly, .zip)"
echo "    2. Drop the zip into  $LIB_DIR/.yosync/incoming/"
echo "    3. Run:  python3 ~/bin/yosync      (or wait for the 6am daemon)"
echo ""
echo "  Every command previews safely with:   --dry-run"
echo "  Repo / docs: https://github.com/TheShulksUp/offlineyt"
echo ""
if [[ -t 0 ]]; then
  read -r -p "  Press Enter to close this window... " _
fi
exit 0