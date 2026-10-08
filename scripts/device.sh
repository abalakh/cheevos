#!/bin/sh
# Read-only device helpers: DEVICE_HOST=<ip> make shot logs.

set -eu

LOG_FILE="/mnt/SDCARD/Saves/spruce/cheevos-MiyooMini.log"
BIN="/mnt/SDCARD/spruce/miyoomini/bin"

if [ -n "${DEVICE_SSH:-}" ]; then
    SSH="$DEVICE_SSH"
elif [ -n "${DEVICE_HOST:-}" ]; then
    SSH="ssh spruce@$DEVICE_HOST"
else
    echo "Set DEVICE_HOST=<ip> (or DEVICE_SSH='ssh user@ip')" >&2
    exit 2
fi

remote() {
    # shellcheck disable=SC2086  # SSH is a command line by design
    $SSH "$@"
}

case "${1:-}" in
    logs)
        remote "tail -n 60 '$LOG_FILE'"
        ;;
    shot)
        out="${2:?usage: device.sh shot FILE.png}"
        # The Mini's framebuffer is upside down; Spruce's own screenshot.sh rotates by 180°.
        remote "$BIN/fbgrab -a /tmp/cheevos-shot.png >/dev/null 2>&1 && cat /tmp/cheevos-shot.png && rm -f /tmp/cheevos-shot.png" >"$out"
        if command -v sips >/dev/null 2>&1; then sips -r 180 "$out" >/dev/null; fi
        echo "Saved $out"
        ;;
    *)
        echo 'usage: device.sh shot FILE.png | logs' >&2
        exit 2
        ;;
esac
