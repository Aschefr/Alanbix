FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    iputils-ping \
    net-tools \
    dnsutils \
    traceroute \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-nodeps.txt ./
RUN pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir --no-deps -r requirements-nodeps.txt

RUN mkdir -p /app/data

COPY . .

# Watch only the source folder: the whole bind-mounted backend (venv, data, uploads) cost ~10% CPU
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "app", "--ws-per-message-deflate", "false"]
