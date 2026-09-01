# L1a scrape image — a THIN wrapper over the PROD server image.
#
# The scrape driver MUST run the REAL server code (beatport/, workers/, curl_cffi)
# so the matchers are identical to the hourly VPS drain — zero vendoring, no
# re-implementation of the X1/X3/X4 platform-id guards. Rather than duplicate
# server/Dockerfile here (a second, drift-prone copy of the whole image), the host
# orchestrator (backfill_beatport.py) builds the prod image directly from the
# ./server context via server/Dockerfile, tags it SERVER_IMAGE, and this file just
# FROMs it. The layer adds nothing but a stable local tag decoupled from whatever
# the server image is called; the driver (scrape_driver.py) is bind-mounted at
# /work at run time (like embed.py in the embedding tool), never baked in.
#
# The prod image already exposes the code at /app and runs as the unprivileged
# `diggy` user (uid 1000) whose ~/.local carries the installed deps — the driver
# does `sys.path.insert(0, "/app")` and runs as that user so the deps resolve.
ARG SERVER_IMAGE=diggy-beatport-server
FROM ${SERVER_IMAGE}
