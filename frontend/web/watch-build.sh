#!/usr/bin/env bash
# Polls src/ for changes and runs `npm run build` automatically.
# No inotify-tools available (no root to install it) — mtime-hash polling
# instead. Not a systemd unit: started manually via nohup, so it won't
# survive a host reboot. Re-launch after a reboot with:
#   cd frontend/web && nohup ./watch-build.sh > watch-build.log 2>&1 & disown
cd "$(dirname "$0")"
LOG="watch-build.log"

echo "[watch-build] started $(date -Iseconds)" >> "$LOG"

last_hash=""
while true; do
    cur_hash=$(find src -type f \( -name '*.ts' -o -name '*.tsx' -o -name '*.css' \) -printf '%T@ %p\n' 2>/dev/null | sort | md5sum)
    if [ "$cur_hash" != "$last_hash" ]; then
        if [ -n "$last_hash" ]; then
            echo "[watch-build] change detected $(date -Iseconds) — rebuilding" >> "$LOG"
            if npm run build >> "$LOG" 2>&1; then
                echo "[watch-build] build OK $(date -Iseconds)" >> "$LOG"
            else
                echo "[watch-build] BUILD FAILED $(date -Iseconds) — previous dist/ left in place" >> "$LOG"
            fi
        fi
        last_hash="$cur_hash"
    fi
    sleep 3
done
