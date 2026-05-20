FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY backend/ ./backend/

RUN pip install --no-cache-dir -e "."

EXPOSE 8000

CMD ["uvicorn", "nkz_soil.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
