FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install sqlite3 and system CA certs
RUN apt-get update && \
    apt-get install -y sqlite3 ca-certificates && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install pip-system-certs to use system CA certificates
RUN pip install --no-cache-dir pip-system-certs && \
    ln -s /usr/local/lib/python3.11/site-packages/pip_system_certs/wrapt_requests.py \
          /usr/local/lib/python3.11/site-packages/requests.pth

COPY . .

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]