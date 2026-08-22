# PostgreSQL 16 + pgvector (C9.a — audio-embedding storage / ANN search).
#
# Built from source on Alpine. The base postgres:16-alpine is itself compiled
# from source WITH LLVM, so a plain `make` tries to emit JIT bitcode with the
# exact clang it was built against (clang-21), which is not shipped in the apk
# repos → build fails with "clang-21: No such file or directory". Passing
# `with_llvm=no` skips the bitcode step entirely (the extension runs fine without
# JIT, just no JIT-accelerated expressions), removing the clang/LLVM dependency.
# `OPTFLAGS=""` drops pgvector's default `-march=native` so the binary stays
# portable across the build and runtime CPUs. Server headers are already present
# in the base image (/usr/local/include/postgresql/server), so only build-base +
# git are needed; they go in a virtual apk group removed afterwards to keep the
# runtime image lean.
FROM postgres:16-alpine

ARG PGVECTOR_VERSION=v0.8.0

RUN set -eux; \
    apk add --no-cache --virtual .build-deps \
        build-base \
        git; \
    git clone --branch "${PGVECTOR_VERSION}" --depth 1 \
        https://github.com/pgvector/pgvector.git /tmp/pgvector; \
    cd /tmp/pgvector; \
    make OPTFLAGS="" with_llvm=no; \
    make OPTFLAGS="" with_llvm=no install; \
    cd /; \
    rm -rf /tmp/pgvector; \
    apk del .build-deps
