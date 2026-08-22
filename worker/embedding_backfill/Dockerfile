FROM python:3.11-slim

# ffmpeg = MP3 decode backend (essentia MonoLoader decodes via libav/ffmpeg)
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends ffmpeg wget \
    && rm -rf /var/lib/apt/lists/*

# Discogs-EffNet embedding graph (feature extractor, C9 v1 model frozen at C9.0-bis).
# Embeddings node = "PartitionedCall:1" (1280-d penultimate); "PartitionedCall:0" = genre logits.
RUN mkdir -p /models \
    && wget -q https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb \
         -O /models/discogs-effnet-bs64-1.pb

# essentia-tensorflow ships TensorflowPredictEffnetDiscogs (the standard essentia wheel does not)
RUN pip install --no-cache-dir essentia-tensorflow numpy requests

WORKDIR /work
# embed.py + the candidates CSV are bind-mounted at run time (-v <workdir>:/work)
