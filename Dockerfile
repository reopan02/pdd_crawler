
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies if any
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy all necessary files for installation first
COPY pyproject.toml README.md ./
COPY src/ ./src/

# Install pip and dependencies
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .

# Copy the rest of the application data
COPY cookies/ ./cookies/
COPY output/ ./output/

# Create static directory and copy frontend files
RUN mkdir -p /app/src/pdd_crawler/web/static && \
    echo "Static files will be served from web/static"

# Copy static files to the installed package location
COPY src/pdd_crawler/web/static/index.html /usr/local/lib/python3.12/site-packages/pdd_crawler/web/static/

# Expose the application port
EXPOSE 8000

# Command to run the application
CMD ["pdd_web"]
