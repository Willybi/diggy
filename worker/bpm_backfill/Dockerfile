FROM python:3.11-slim

# ffmpeg = MP3 decode backend (essentia's MonoLoader decodes via libav/ffmpeg)
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# BPM-only engine (E2.a decision): essentia standard, NO librosa/tensorflow/keyfinder
RUN pip install --no-cache-dir essentia requests

WORKDIR /work
# analyze_bpm.py + the candidates CSV are bind-mounted at run time (-v <workdir>:/work)
