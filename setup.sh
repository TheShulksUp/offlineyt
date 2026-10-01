#!/usr/bin/env bash
# OfflineYT / yosync — Linux installer.
# Installs python deps, yt-dlp, ffmpeg, yosync itself, and a daily
# systemd user timer (or a cron fallback) at 6am.
#
#   curl -fsSL https://raw.githubusercontent.com/TheShulksUp/offlineyt/main/setup.sh | bash
#
# Env overrides:
#   YOSYNC_DIR   install prefix (default ~/.local/share/yosync)
#   YOSYNC_DEST  library folder (default ~/Videos/OfflineYouTube)
#   YOSYNC_PYTHON python interpreter (default python3)

set -euo pipefail

YOSYNC_DIR="${YOSYNC_DIR:-$HOME/.local/share/yosync}"
YOSYNC_DEST="${YOSYNC_DEST:-$HOME/Videos/OfflineYouTube}"
YOSYNC_PYTHON="${YOSYNC_PYTHON:-python3}"
UNIT_DIR="$HOME/.config/systemd/user"
BIN_DIR="$HOME/.local/bin"
DRY_RUN="${DRY_RUN:-0}"

say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33mwarn:\033[0m %s\n' "$*" >&2; }
die() { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

run() {
  if [ "$DRY_RUN" = "1" ]; then
    printf '   [dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

# --- sanity -----------------------------------------------------------------

[ "$(uname -s)" = "Linux" ] || die "setup.sh is for Linux; macOS users should use Setup.command"

command -v "$YOSYNC_PYTHON" >/dev/null 2>&1 || die "$YOSYNC_PYTHON not found (install python3 first)"
say "python: $($YOSYNC_PYTHON --version 2>&1)"

# --- dependencies -----------------------------------------------------------

need_sudo=0
if [ "$(id -u)" -ne 0 ]; then
  need_sudo=1
fi

install_pkgs() {
  if command -v apt-get >/dev/null 2>&1; then
    run sudo apt-get update
    run sudo apt-get install -y "$@"
  elif command -v dnf >/dev/null 2>&1; then
    run sudo dnf install -y "$@"
  elif command -v pacman >/dev/null 2>&1; then
    run sudo pacman -Sy --noconfirm "$@"
  elif command -v apk >/dev/null 2>&1; then
    run sudo apk add --no-cache "$@"
  else
    warn "unknown package manager; install these yourself: $*"
  fi
}

if ! command -v yt-dlp >/dev/null 2>&1; then
  say "installing yt-dlp"
  install_pkgs ffmpeg
  if command -v pipx >/dev/null 2>&1; then
    run pipx install yt-dlp
  elif command -v pip3 >/dev/null 2>&1; then
    run pip3 install --user -U yt-dlp
  else
    run "$YOSYNC_PYTHON" -m pip install --user -U yt-dlp
  fi
else
  say "yt-dlp already installed: $(yt-dlp --version 2>/dev/null | head -1)"
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  say "installing ffmpeg"
  install_pkgs ffmpeg
else
  say "ffmpeg already installed"
fi

# --- yosync -----------------------------------------------------------------

say "installing yosync into $YOSYNC_DIR"
mkdir -p "$YOSYNC_DIR" "$BIN_DIR" "$YOSYNC_DEST"
if [ -f ./bin/yosync ]; then
  SRC=./bin/yosync
else
  SRC="$YOSYNC_DIR/yosync.new"
  curl -fsSL -o "$SRC" \
    https://raw.githubusercontent.com/TheShulksUp/offlineyt/main/bin/yosync
fi
run install -m 755 "$SRC" "$YOSYNC_DIR/yosync"
run rm -f "$YOSYNC_DIR/yosync.new"

if [ "$DRY_RUN" = "1" ]; then
  say "[dry-run] would write wrapper $BIN_DIR/yosync"
else
  cat > "$BIN_DIR/yosync" <<EOF
#!/usr/bin/env bash
exec "$YOSYNC_PYTHON" "$YOSYNC_DIR/yosync" "\$@"
EOF
  chmod +x "$BIN_DIR/yosync"
  say "wrapper: $BIN_DIR/yosync"
fi

# initial config (never overwrites an existing one)
if [ -f "$HOME/.config/yosync/config.json" ]; then
  say "existing config kept"
else
  run "$BIN_DIR/yosync" --dest "$YOSYNC_DEST" --silent
fi

# --- daily sync: systemd user timer, cron fallback --------------------------

install_timer() {
  say "installing systemd user timer (daily 06:00)"
  mkdir -p "$UNIT_DIR"
  cat > "$UNIT_DIR/yosync.service" <<EOF
[Unit]
Description=OfflineYT sync (yosync)

[Service]
Type=oneshot
ExecStart=$BIN_DIR/yosync --drive --silent
EOF
  cat > "$UNIT_DIR/yosync.timer" <<EOF
[Unit]
Description=Run OfflineYT sync daily at 06:00

[Timer]
OnCalendar=*-*-* 06:00:00
Persistent=true

[Install]
WantedBy=timers.target
EOF
  run systemctl --user daemon-reload
  run systemctl --user enable --now yosync.timer
  run loginctl enable-linger "$USER" 2>/dev/null || \
    warn "enable 'linger' for your user to run timers without being logged in"
}

install_cron() {
  say "systemd user timers unavailable; using cron fallback"
  mkdir -p "$HOME/.config/yosync"
  CRON_LINE="0 6 * * * $BIN_DIR/yosync --drive --silent >> $YOSYNC_DEST/logs/cron.log 2>&1"
  if crontab -l 2>/dev/null | grep -q "yosync --drive"; then
    say "cron entry already present"
  else
    ( crontab -l 2>/dev/null; echo "$CRON_LINE" ) | crontab -
  fi
}

if [ "$DRY_RUN" = "1" ]; then
  run mkdir -p "$UNIT_DIR"
elif command -v systemctl >/dev/null 2>&1; then
  if install_timer; then :; else
    warn "systemd timer install failed; falling back to cron"
    install_cron
  fi
else
  install_cron
fi

# --- done -------------------------------------------------------------------

cat <<EOF

  yosync is installed.

    $BIN_DIR/yosync --serve     edit every setting in your browser
    $BIN_DIR/yosync --dry-run   preview a sync
    $BIN_DIR/yosync             run a sync now

  Library: $YOSYNC_DEST
  Logs:    $YOSYNC_DEST/logs/sync.log

  Next: export your YouTube watch history at takeout.google.com
  (YouTube and YouTube Music, JSON, export once) and drop the zip into:
    $YOSYNC_DEST/inbox

EOF
