
FROM debian:bookworm-slim

# Install Chrome, VNC, noVNC, and socat for port forwarding
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg ca-certificates \
    socat \
    xvfb x11vnc fluxbox \
    novnc websockify \
    fonts-wqy-zenhei fonts-noto-cjk \
    procps dbus-x11 \
    socat \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y --no-install-recommends google-chrome-stable \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -s /bin/bash chrome
USER chrome
WORKDIR /home/chrome

# Default Chrome user data directory (mount as volume for persistence)
RUN mkdir -p /home/chrome/chrome-data

# Expose ports: 9222=CDP, 5900=VNC, 6080=noVNC
EXPOSE 9222 5900 6080

# Startup script
COPY --chown=chrome:chrome entrypoint.sh /home/chrome/entrypoint.sh
RUN chmod +x /home/chrome/entrypoint.sh

ENTRYPOINT ["/home/chrome/entrypoint.sh"]
