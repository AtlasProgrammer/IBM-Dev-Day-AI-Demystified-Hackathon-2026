FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Install dependencies
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy application code
COPY backend backend

# Code Engine typically routes traffic to PORT (often 8080)
ENV HOST=0.0.0.0 \
    PORT=8080 \
    RELOAD=false

EXPOSE 8080

CMD ["python", "-m", "backend"]
