FROM python:3.11-slim

# ffmpeg = MP3 decode backend for librosa/audioread; essentia decodes via its own libav
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir essentia librosa soundfile numpy requests

WORKDIR /work
# benchmark.py, camelot.py, ground_truth.csv are bind-mounted at run time (-v .../e2a:/work)
