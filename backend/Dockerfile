FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Railway provides PORT env variable, fallback to 8000 for local
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
