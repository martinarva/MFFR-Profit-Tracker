FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install sqlite3 CLI for debugging or shell access (optional but useful)
RUN apt-get update && apt-get install -y sqlite3 && apt-get clean

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]