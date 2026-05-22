FROM python:3.12-slim

# Install build dependencies for py-solc-x and native extensions
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-install Solidity compiler so it's ready at runtime
RUN python -c "from solcx import install_solc; install_solc('0.8.21')"

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
