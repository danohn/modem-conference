#!/bin/sh
# Required clean-OS acceptance check; no Python is used by the test harness.
set -eu

for name in python python3 uv ffmpeg ffprobe; do
    if command -v "$name" >/dev/null 2>&1; then
        echo "Unexpected system dependency in clean runtime: $name" >&2
        exit 1
    fi
done
if dpkg-query -W -f='${binary:Package}\n' | grep -Eq '^(python|libpython|uv(:|$)|ffmpeg(:|$))'; then
    echo 'Clean OS must not contain an installed Python, uv or FFmpeg package' >&2
    exit 1
fi

temporary=$(mktemp -d)
trap 'rm -rf "$temporary"' EXIT HUP INT TERM
export HOME="$temporary"
export XDG_RUNTIME_DIR="$temporary/runtime"
export XDG_CACHE_HOME="$temporary/xdg-cache"
export QT_QPA_PLATFORM=offscreen
export MODEM_CONFERENCE_CONFIG_DIR="$temporary/settings"
export MODEM_CONFERENCE_CACHE_DIR="$temporary/cache"
export MODEM_CONFERENCE_LOG_DIR="$temporary/logs"
mkdir -p "$XDG_RUNTIME_DIR"
chmod 700 "$XDG_RUNTIME_DIR"

# Report optional as well as required unresolved shared-library dependencies in
# one pass. Actual launch checks below remain authoritative; an unused plugin
# may legitimately require a desktop service that this offscreen test omits.
find /opt/app -type f -name '*.so*' -exec ldd {} + 2>/dev/null | grep 'not found' | sort -u || true

helper_report=$(timeout 45 /opt/app/helper/modem-conference-helper --self-test)
printf '%s\n' "$helper_report"
printf '%s\n' "$helper_report" | grep -Eq '"helper":[[:space:]]*true'
printf '%s\n' "$helper_report" | grep -Eq '"asset":[[:space:]]*true'
worker_report=$(timeout 45 /opt/app/helper/modem-conference-helper worker --self-test)
printf '%s\n' "$worker_report"
printf '%s\n' "$worker_report" | grep -Eq '"ready":[[:space:]]*true'
printf '%s\n' "$worker_report" | grep -Eq '"protocol_version":[[:space:]]*1'
timeout 45 /opt/app/modem-conference --smoke-test
echo 'Clean Ubuntu runtime passed: GUI + helper + protocol resources, no system Python/uv/FFmpeg.'
