#!/bin/bash
set -e

DISPLAY=:99
export DISPLAY

# Clean up any existing locks
rm -f /tmp/.X99-lock

# Start virtual framebuffer
Xvfb $DISPLAY -screen 0 1920x1080x24 -ac &
sleep 2

# Start window manager
fluxbox &
sleep 1

# Start VNC server (no password for LAN use; add -passwd for security)
x11vnc -display $DISPLAY -forever -shared -nopw -rfbport 5900 &

# Start noVNC web client
websockify --web /usr/share/novnc 6080 localhost:5900 &

# Clean stale Chrome singleton lock files in persisted profile.
# These files can remain after unclean shutdown/restart and cause:
# "The profile appears to be in use by another Google Chrome process"
rm -f /home/chrome/chrome-data/SingletonLock \
      /home/chrome/chrome-data/SingletonSocket \
      /home/chrome/chrome-data/SingletonCookie

# Launch Chrome with CDP bound to localhost (Chrome may force loopback)
google-chrome-stable \
    --remote-debugging-port=9222 \
    --remote-debugging-address=127.0.0.1 \
    --user-data-dir=/home/chrome/chrome-data \
    --no-first-run \
    --no-default-browser-check \
    --disable-background-networking \
    --disable-sync \
    --disable-translate \
    --disable-features=TranslateUI \
    --lang=zh-CN \
    --window-size=1920,1080 \
    --start-maximized \
    --no-sandbox \
    --disable-dev-shm-usage \
    --disable-gpu \
    --disable-background-networking \
    --disable-cloud-import \
    --disable-component-extensions-with-background-pages \
    --disable-default-apps \
    --disable-extensions \
    --disable-gcm-key-migration \
    --disable-notifications \
    --disable-push-api \
    --disable-web-push \
    --no-pings \
    "https://mms.pinduoduo.com" &

# Expose CDP to container network on 9223 via socat
echo "Starting CDP proxy: 0.0.0.0:9223 -> 127.0.0.1:9222"
exec socat TCP-LISTEN:9223,fork,bind=0.0.0.0,reuseaddr TCP:127.0.0.1:9222
