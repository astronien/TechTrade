FROM python:3.9-slim

# Install system dependencies (libpq-dev for psycopg2 if needed, though binary handles most)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Default PORT
ENV PORT=10000

# Start command using gunicorn
CMD gunicorn --workers 4 --bind 0.0.0.0:$PORT app:app
