FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for OpenCV
RUN apt-get update && apt-get install -y \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements-api.txt .
RUN pip install --no-cache-dir -r requirements-api.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000

# Start command with shell to expand $PORT
CMD uvicorn cv_api:app --host 0.0.0.0 --port ${PORT:-8000}
