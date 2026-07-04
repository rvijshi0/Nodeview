FROM python:3.11-slim

WORKDIR /app

# Install system utilities needed for building database adapters
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    zip \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source modules
COPY . .

EXPOSE 8000

# Start server using uvicorn binding to all interfaces
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
