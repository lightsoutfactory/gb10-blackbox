#!/bin/sh
# Install the black box (a reading a minute) and, with --clock-cap MHZ, the GPU clock cap.
#   sudo ./install.sh                      the black box only
#   sudo ./install.sh --clock-cap 2000     and cap the GPU clock at 2000 MHz from the next boot on (and now)
set -eu
[ "$(id -u)" = 0 ] || { echo "run it with sudo"; exit 1; }
cd "$(dirname "$0")"
CAP=""
if [ "${1:-}" = "--clock-cap" ]; then
  CAP="${2:-}"
  case "$CAP" in ''|*[!0-9]*) echo "--clock-cap takes a number of MHz, for example 2000"; exit 1;; esac
fi
install -m 755 gb10-blackbox /usr/local/bin/gb10-blackbox
install -m 644 systemd/gb10-blackbox.service systemd/gb10-blackbox.timer /etc/systemd/system/
if [ -n "$CAP" ]; then
  sed "s/@MHZ@/$CAP/g" systemd/gb10-clock-cap.service > /etc/systemd/system/gb10-clock-cap.service
  chmod 644 /etc/systemd/system/gb10-clock-cap.service
fi
systemctl daemon-reload
systemctl enable --now gb10-blackbox.timer
[ -n "$CAP" ] && systemctl enable --now gb10-clock-cap.service
/usr/local/bin/gb10-blackbox now
echo "installed. Readings go to /var/log/gb10-blackbox.log, one a minute."
echo "after an unexpected power-off:  gb10-blackbox why      how hot it runs:  gb10-blackbox bands"
