FROM python:3.9-slim

WORKDIR /app

# Install dependencies first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY static/ static/

# Create data directories for runtime
# - radar_history: fetched from GitHub on first startup if not present
# - submissions.json: created on first submission
RUN mkdir -p data/radar_history

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
