#!/usr/bin/env bash
set -euo pipefail

SYSTEMD_USER_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cp "$SCRIPT_DIR/psntui-sync.service" "$SYSTEMD_USER_DIR/"
cp "$SCRIPT_DIR/psntui-sync.timer" "$SYSTEMD_USER_DIR/"

systemctl --user daemon-reload
systemctl --user enable psntui-sync.timer
systemctl --user start psntui-sync.timer

echo "✅ psnTUI sync timer installed and started!"
echo "   Runs every 4 hours (15 min after boot)"
echo ""
echo "Check status: systemctl --user status psntui-sync.timer"
echo "View logs:    journalctl --user -u psntui-sync.service -n 20"
