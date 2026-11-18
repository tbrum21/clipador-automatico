FROM python:3.12-slim-bookworm AS whisper-build

ARG WHISPER_VERSION=v1.8.2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 --branch "${WHISPER_VERSION}" https://github.com/ggml-org/whisper.cpp.git /src/whisper \
    && cmake -S /src/whisper -B /src/whisper/build \
       -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
       -DGGML_NATIVE=OFF -DWHISPER_BUILD_TESTS=OFF -DWHISPER_BUILD_SERVER=OFF \
    && cmake --build /src/whisper/build --target whisper-cli -j 2

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    WHISPER_BIN=/usr/local/bin/whisper-cli \
    WHISPER_MODEL=/models/ggml-base.bin \
    ENCODER=libx264

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg fonts-liberation libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 clipflow \
    && useradd --uid 1000 --gid clipflow --create-home clipflow
COPY --from=whisper-build /src/whisper/build/bin/whisper-cli /usr/local/bin/whisper-cli
WORKDIR /app
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.txt -c requirements.lock
COPY --chown=clipflow:clipflow clipflow ./clipflow
COPY --chown=clipflow:clipflow templates.json ./templates.json
COPY --chown=clipflow:clipflow docker ./docker
RUN mkdir -p /app/data /models /input && chown -R clipflow:clipflow /app /models /input
USER clipflow
CMD ["python", "-m", "clipflow.main"]
