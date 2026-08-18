# Ana uygulama (YOLO+SAHI pipeline + VRAG + backend + LLM karar servisi) imajı.
# Yalnızca kod + bağımlılıkları içerir — büyük/sık değişen veriler (data/,
# output/, models/, karar_servisi/data/ — data/ altında referans/ ve videos/
# de dahil) docker-compose.yml'de bind-mount edilir, imaja gömülmez (image
# küçük kalır, veri güncellemesi için rebuild gerekmez).
#
# GPU: CUDA'lı torch wheel'i pip üzerinden kendi CUDA runtime'ını (nvidia-*
# paketleri) getirir — CUDA'lı bir base image şart değil, host'ta NVIDIA
# sürücü + nvidia-container-toolkit yeterli (bkz. docker-compose.yml notu).
FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 libsm6 libxext6 libxrender1 curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# --- karar_servisi (operational_decision) bağımlılıkları: uv.lock ile deterministik ---
COPY karar_servisi/pyproject.toml karar_servisi/uv.lock /app/karar_servisi/
RUN cd /app/karar_servisi && uv sync --frozen --no-dev

# --- Ana pipeline'ın ekstra paketleri (pyproject.toml'da olmayanlar) ---
COPY docker/requirements-pipeline.txt /app/docker/requirements-pipeline.txt
RUN /app/karar_servisi/.venv/bin/pip install --no-cache-dir -r /app/docker/requirements-pipeline.txt

# --- Kaynak kod ---
COPY src/ /app/src/
COPY backend/ /app/backend/
COPY karar_servisi/src/ /app/karar_servisi/src/

ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# main.py subprocess.Popen ile karar servisini sys.executable kullanarak
# başlatıyor — bu yüzden container'ı da /app/karar_servisi/.venv/bin/python ile
# çalıştırmak şart (aksi halde alt-süreç farklı/eksik bir yorumlayıcı kullanır).
WORKDIR /app/backend
CMD ["/app/karar_servisi/.venv/bin/python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
