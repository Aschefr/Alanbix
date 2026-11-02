#!/bin/sh
# Starts as root only to hand the data folders to an ordinary account, then runs the app as that account.
# PUID / PGID choose the account (default 1000:1000; on Unraid, 99:100).
set -e

PUID="${PUID:-1000}"
PGID="${PGID:-1000}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p /app/data /app/static/uploads/games
    for dir in /app/data /app/static/uploads; do
        # Data written by older versions (run as root) or another PUID: hand it over, once
        if [ -n "$(find "$dir" \( ! -user "$PUID" -o ! -group "$PGID" \) -print -quit)" ]; then
            echo "[Startup] Giving $dir to $PUID:$PGID"
            chown -R "$PUID:$PGID" "$dir"
        fi
    done
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups --inh-caps=-all -- "$@"
fi

exec "$@"
