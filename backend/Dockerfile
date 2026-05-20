FROM python:3.12-slim

WORKDIR /app

# Install git to clone SDK from source (not on PyPI)
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    rm -rf /var/lib/apt/lists/* && \
    git clone --depth 1 https://github.com/nkz-os/nkz.git /tmp/nkz-src && \
    pip install --no-cache-dir /tmp/nkz-src/services/nkz-platform-sdk && \
    rm -rf /tmp/nkz-src

COPY pyproject.toml ./
COPY backend/ ./backend/

RUN pip install --no-cache-dir -e "."

EXPOSE 8000

CMD ["uvicorn", "nkz_soil.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
