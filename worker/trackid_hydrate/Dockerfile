# L1a trackid-hydrate image — the PROD server image + EffNet (for the later BPM /
# embedding lots). ONE container that carries: the real server code (workers/ +
# beatport/ + curl_cffi at /app, so the reused matchers are byte-identical to the
# hourly VPS drain), Essentia + ffmpeg (already in the server image for the E2.c BPM
# analysis), and the Discogs-EffNet graph (added here for the C9 audio embedding).
#
# Like worker/beatport_backfill/Dockerfile this is a THIN wrapper: the host
# orchestrator (L2) builds the prod image from the ./server context via
# server/Dockerfile, tags it SERVER_IMAGE, and this file FROMs it — no drift-prone
# copy of the whole image. The drivers (enrich_driver.py + the later lots) are
# bind-mounted at /work at run time, never baked in.
#
# The server image ends on `USER diggy` (uid 1000) with its deps under
# /home/diggy/.local; we switch to root only to apt-get wget + fetch the graph, then
# back to diggy for the --user pip install so PATH (/home/diggy/.local/bin) resolves.
ARG SERVER_IMAGE=diggy-trackid-hydrate-server
FROM ${SERVER_IMAGE}

USER root
# wget = fetch the EffNet graph (the slim base + server image carry neither wget nor curl)
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends wget \
    && rm -rf /var/lib/apt/lists/*

# Discogs-EffNet embedding graph baked into the image (same model/node as
# worker/embedding_backfill: embeddings = "PartitionedCall:1", 1280-d penultimate).
RUN mkdir -p /models \
    && wget -q https://essentia.upf.edu/models/feature-extractors/discogs-effnet/discogs-effnet-bs64-1.pb \
         -O /models/discogs-effnet-bs64-1.pb \
    && chown -R diggy:diggy /models

USER diggy
# essentia-tensorflow is a SUPERSET of the plain `essentia` wheel already installed in
# the server image (requirements.txt: essentia==2.1b6.dev1389, for BPM): it ships the
# SAME standard algorithms (RhythmExtractor2013 → BPM parity) PLUS
# TensorflowPredictEffnetDiscogs (EffNet embeddings). Both packages own the `essentia`
# module, so installing the tensorflow build ON TOP would collide — uninstall the plain
# wheel first, then install the tensorflow build PINNED to the same version so the BPM
# C++ core stays identical to the VPS drain. Kept as the diggy --user install so it
# lands in /home/diggy/.local alongside the rest of the server deps.
RUN pip uninstall -y essentia \
    && pip install --user --no-cache-dir essentia-tensorflow==2.1b6.dev1389
