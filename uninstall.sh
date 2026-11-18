#!/bin/sh
# Remove the timer, the clock cap (the GPU clock is reset) and the program. The record stays unless --purge.
set -eu
[ "$(id -u)" = 0 ] || { echo "run it with sudo"; exit 1; }
systemctl disable --now gb10-blackbox.timer 2>/dev/null || true
systemctl disable --now gb10-clock-cap.service 2>/dev/null || true
rm -f /etc/systemd/system/gb10-blackbox.service /etc/systemd/system/gb10-blackbox.timer \
      /etc/systemd/system/gb10-clock-cap.service /usr/local/bin/gb10-blackbox
systemctl daemon-reload
[ "${1:-}" = "--purge" ] && rm -f /var/log/gb10-blackbox.log
echo "removed."
