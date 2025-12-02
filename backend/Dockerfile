FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y \
    build-essential \
    poppler-utils \
    tesseract-ocr \
    libtesseract-dev \
    libgl1 \
    libgomp1 \
    libopenblas-dev \
    cmake \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV CHROMA_DB_DIR=/data/chroma
RUN mkdir -p /data/chroma

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
