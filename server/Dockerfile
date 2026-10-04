FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY server/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY server/ ./server/
COPY 合拍-交互原型.html ./合拍-交互原型.html

EXPOSE 8080
CMD ["sh", "-c", "cd /app/server && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
