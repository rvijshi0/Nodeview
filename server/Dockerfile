FROM python:3.11-slim

WORKDIR /app

# Install system utilities needed for building database adapters
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    zip \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY server/ .

# Copy agent code to /agent
COPY agent/ /agent/

EXPOSE 8000

# Start server using uvicorn binding to all interfaces
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
