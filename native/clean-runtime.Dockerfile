FROM ubuntu:24.04

# Desktop OS libraries only. Python, uv, FFmpeg and build tools are deliberately
# absent. Qt and Python application runtimes come exclusively from the archive.
RUN apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    libegl1 libopengl0 libgl1 libxcb-cursor0 libxkbcommon-x11-0 \
    libpulse0 libdbus-1-3 libfontconfig1 fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY clean-runtime.sh /usr/local/bin/check-native-runtime
ENTRYPOINT ["/bin/sh", "/usr/local/bin/check-native-runtime"]
