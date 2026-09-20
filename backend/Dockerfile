FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for PyMuPDF and python-docx
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application code
COPY app/ ./app/
COPY storage/ ./storage/

# Ensure no temporary or runtime database files are baked into image
RUN rm -f /app/storage/*.db /app/storage/*.sqlite3

# Environment defaults
ENV ENVIRONMENT=production
ENV PORT=8000
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
