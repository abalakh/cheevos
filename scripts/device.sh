#!/bin/sh
# Developer helper for a SpruceOS device on the network. Runs on the dev machine.
#
#   scripts/device.sh deploy      copy dist/App/Cheevos to the device (run `make package` first)
#   scripts/device.sh launch      start Cheevos remotely (same handoff as the Apps menu)
#   scripts/device.sh stop        ask Cheevos to exit (PyUI comes back)
#   scripts/device.sh logs        show the app log and the last stderr
#   scripts/device.sh shot FILE   save the device screen as PNG
#   scripts/device.sh press KEY…  tap buttons: up down left right a b x y l1 r1 start select
#                                 (only while Cheevos runs: stops at the first refused tap)
#
# Connection: DEVICE_SSH (full ssh command, e.g. "ssh spruce@192.168.0.105"), or
# DEVICE_HOST (used as "ssh spruce@$DEVICE_HOST").
#
# Safety: the only path this script deletes is $APP_DIR/cheevos (the app's own code).
# Process patterns use the [x] trick so pgrep/pkill never match the remote shell itself.

set -eu

APP_DIR="/mnt/SDCARD/App/Cheevos"
LOG_FILE="/mnt/SDCARD/Saves/spruce/cheevos-MiyooMini.log"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
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

key_code() {
    case "$1" in
        up) echo 103 ;; down) echo 108 ;; left) echo 105 ;; right) echo 106 ;;
        a) echo 57 ;; b) echo 29 ;; x) echo 42 ;; y) echo 56 ;;
        l1) echo 18 ;; r1) echo 20 ;; start) echo 28 ;; select) echo 97 ;;
        *) echo "unknown key: $1" >&2; return 1 ;;
    esac
}

case "${1:-}" in
    deploy)
        [ -d "$REPO/dist/App/Cheevos" ] || { echo "run 'make package' first" >&2; exit 1; }
        remote "rm -rf '$APP_DIR/cheevos' && mkdir -p '$APP_DIR'"
        # ustar without macOS metadata: busybox tar on the device chokes on pax/xattr headers.
        COPYFILE_DISABLE=1 tar -C "$REPO/dist/App/Cheevos" --format ustar -cf - . |
            remote "tar -xf - -C '$APP_DIR' && chmod +x '$APP_DIR/launch.sh' && sync"
        echo "Deployed to $APP_DIR"
        ;;
    launch)
        remote "
            if pgrep -f 'python3[.]10 -m [c]heevos' >/dev/null; then echo 'Cheevos is already running'; exit 0; fi
            if pgrep -f '[r]a32[.]|[r]etroarch' >/dev/null; then echo 'A game is running; not launching' >&2; exit 1; fi
            printf '%s\n' 'cd \"$APP_DIR\"; chmod a+x \"$APP_DIR/launch.sh\"; \"$APP_DIR/launch.sh\"' > /tmp/cmd_to_run.sh
            pkill -TERM -f 'main-ui/[m]ainui[.]py' && echo 'PyUI asked to exit; principal.sh launches Cheevos'
        "
        ;;
    stop)
        remote "pkill -TERM -f 'python3[.]10 -m [c]heevos' && echo 'Cheevos asked to exit' || echo 'Cheevos is not running'"
        ;;
    logs)
        remote "tail -n 60 '$LOG_FILE' 2>/dev/null; echo '--- stderr'; tail -n 30 /tmp/cheevos-stderr.log 2>/dev/null || true"
        ;;
    shot)
        out="${2:?usage: device.sh shot FILE.png}"
        # The Mini's framebuffer is upside down; Spruce's own screenshot.sh rotates by 180°.
        remote "$BIN/fbgrab -a /tmp/cheevos-shot.png >/dev/null 2>&1 && cat /tmp/cheevos-shot.png && rm -f /tmp/cheevos-shot.png" >"$out"
        if command -v sips >/dev/null 2>&1; then sips -r 180 "$out" >/dev/null; fi
        echo "Saved $out"
        ;;
    press)
        shift
        for key in "$@"; do
            code="$(key_code "$key")"
            # Only ever tap Cheevos: once it exits, taps reach Spruce's menu and can start a game.
            remote "
                pgrep -f 'python3[.]10 -m [c]heevos' >/dev/null || { echo 'Cheevos is not running: not pressing $key' >&2; exit 3; }
                $BIN/send_event /dev/input/event0 $code:1; usleep 80000 2>/dev/null || sleep 1; $BIN/send_event /dev/input/event0 $code:0
            "
            sleep 0.4
        done
        ;;
    *)
        sed -n '2,13p' "$0"
        exit 2
        ;;
esac
