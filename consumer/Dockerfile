FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY consumer.py .

# 로그 저장 디렉토리 (volume mount point)
RUN mkdir -p /logs

CMD ["python", "-u", "consumer.py"]