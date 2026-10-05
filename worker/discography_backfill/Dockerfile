# C14.a Phase 2 benchmark fetch image — a THIN wrapper over the PROD server image.
#
# The fetch driver MUST run the REAL server code (api/utils, workers/, curl_cffi) so
# make_normalized_key + the Deezer HTTP/rate-limit stack are byte-identical to
# ingestion — zero vendoring, so the net-new count matches what production would
# insert. Rather than duplicate server/Dockerfile here (a second, drift-prone copy of
# the whole image), the host orchestrator (benchmark_discography.py) builds the prod
# image directly from the ./server context via server/Dockerfile, tags it SERVER_IMAGE,
# and this file just FROMs it. The layer adds nothing but a stable local tag decoupled
# from whatever the server image is called; the driver (fetch_driver.py) is bind-mounted
# at /work at run time, never baked in.
#
# The prod image already exposes the code at /app (api/ at /app so `utils` imports,
# workers/ at /app/workers) and runs as the unprivileged `diggy` user (uid 1000) whose
# ~/.local carries the installed deps — the driver does `sys.path.insert(0, "/app")`
# and runs as that user so the deps resolve.
ARG SERVER_IMAGE=diggy-discography-server
FROM ${SERVER_IMAGE}
