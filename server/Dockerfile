FROM python:3.13-slim AS builder
WORKDIR /build
COPY api/requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

FROM python:3.13-slim
# ffmpeg = MP3 decode backend for Essentia's MonoLoader (E2.c BPM analysis of
# Deezer previews). The slim base has no ffmpeg; installed here in the final
# stage. --no-install-recommends + apt list cleanup keep the layer minimal.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -m -u 1000 diggy
COPY --from=builder /root/.local /home/diggy/.local
ENV PATH=/home/diggy/.local/bin:$PATH
WORKDIR /app
COPY api/ /app/
COPY workers/ /app/workers/
RUN chown -R diggy:diggy /app
# Beat writes its schedule to the beat_schedule volume mounted here; the dir must
# pre-exist diggy-owned so Docker propagates that ownership into an empty volume
RUN mkdir -p /var/spool/celery && chown diggy:diggy /var/spool/celery
USER diggy
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
