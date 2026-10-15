#!/usr/bin/env bash

# Deploy the app to the UNO Q over Wi-Fi, or pull the per-run logs back to the PC.

#   ./deploy.sh [--no-follow]   stop the running app, sync app.yaml, python/, sketch/, bricks/ and models/, start this app, check its libraries, follow its logs
#   ./deploy.sh pull <day>      stop the running app, move /app/logs/* into data/<day>/ and leave the app stopped (only between runs)
#   ./deploy.sh run <command>   send a command to the running app (e.g. `run idle`), then show its latest events

# The board is reached through the ssh alias in BOARD (default "unoq", see ~/.ssh/config).
set -euo pipefail

BOARD="${BOARD:-unoq}"
APP_DIR=/home/arduino/ArduinoApps/agv   # app id user:agv
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VERSIONS="$REPO/docs/board-versions.txt"
PATCHED_BRIDGE=sketch/libraries/Arduino_RouterBridge

usage() {
    echo "usage: $0 [--no-follow] | pull <day> | run <command>" >&2
    exit 2
}

stop_running_apps() {
    local id

    for id in $(ssh "$BOARD" arduino-app-cli app list | awk '$(NF-1) ~ /^(running|starting)$/ {print $1}'); do
        echo "Stopping $id"
        ssh "$BOARD" arduino-app-cli app stop "$id"
    done
}

library_lines() {
    grep -oE '(Board platform: |Build platform: |Used library ).*' "$1" | tr -d '\r' || true
}

check_libraries() {
    local out=$1 ok=0

    if [[ -f $VERSIONS ]]; then
        if ! diff <(library_lines "$VERSIONS") <(library_lines "$out"); then
            echo "ERROR: platform/libraries differ from docs/board-versions.txt (< recorded, > now)" >&2
            ok=1
        fi
    else
        echo "WARNING: docs/board-versions.txt does not exist yet, libraries not checked" >&2
    fi

    if [[ -d $REPO/$PATCHED_BRIDGE ]]; then
        if ! library_lines "$out" | grep -qE "^Used library Arduino_RouterBridge .* in .*/$PATCHED_BRIDGE$"; then
            echo "ERROR: Arduino_RouterBridge is not the patched copy in $PATCHED_BRIDGE" >&2
            ok=1
        fi
    else
        echo "WARNING: $PATCHED_BRIDGE does not exist yet, the bridge thread has the 500-byte stack" >&2
    fi

    return $ok
}

deploy() {
    local follow=$1 out
    cd "$REPO"
    stop_running_apps
    ssh "$BOARD" mkdir -p "$APP_DIR"
    rsync -a --delete --exclude __pycache__ app.yaml python sketch bricks models "$BOARD:$APP_DIR/"

    out=$(mktemp)
    trap "rm -f '$out'" EXIT
    ssh "$BOARD" arduino-app-cli app start "$APP_DIR" | tee "$out"
    if ! check_libraries "$out"; then
        echo "Stopping the app" >&2
        ssh "$BOARD" arduino-app-cli app stop "$APP_DIR"
        exit 1
    fi

    if [[ $follow == yes ]]; then
        ssh -t "$BOARD" arduino-app-cli app logs "$APP_DIR" --follow
    fi
}

pull() {
    local day=$1 dest
    [[ $day =~ ^[A-Za-z0-9_-]+$ ]] || usage
    dest="$REPO/data/$day"

    stop_running_apps

    if ! ssh "$BOARD" test -d "$APP_DIR/logs"; then
        echo "No $APP_DIR/logs on the board"
        return
    fi

    mkdir -p "$dest"
    rsync -a --ignore-existing --remove-source-files "$BOARD:$APP_DIR/logs/" "$dest/"
    echo "Pulled into data/$day/. Files left in the board's logs/ (name collisions):"
    ssh "$BOARD" find "$APP_DIR/logs" -type f
}

run_command() {
    local cmd="$*" name
    [[ $cmd =~ ^[A-Za-z0-9_.\ -]+$ ]] || usage
    name=$(date +%s%N)
    ssh "$BOARD" "mkdir -p $APP_DIR/cmd && printf '%s\n' '$cmd' > $APP_DIR/cmd/.$name.tmp && mv $APP_DIR/cmd/.$name.tmp $APP_DIR/cmd/$name.cmd"
    sleep 1
    ssh "$BOARD" "tail -n 3 \"\$(ls -t $APP_DIR/logs/*_events.csv | head -1)\""
}

case "${1:-}" in
    "") deploy yes ;;
    --no-follow) [[ $# -eq 1 ]] || usage; deploy no ;;
    pull) [[ $# -eq 2 ]] || usage; pull "$2" ;;
    run) [[ $# -ge 2 ]] || usage; shift; run_command "$@" ;;
    *) usage ;;
esac
