# syntax=docker/dockerfile:1

# ---- jabridge: community Jabra device service (Apache-2.0), built from a pinned tag ----
ARG GO_IMAGE=golang:1.27-alpine
FROM ${GO_IMAGE} AS jabridge
ARG JABRIDGE_REF=v1.7.1
RUN apk add --no-cache git
RUN git clone --depth 1 --branch "${JABRIDGE_REF}" https://github.com/Watchdog0x/jabridge /src
WORKDIR /src
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/jabridge ./cmd/jabridge

# ---- runtime ----
FROM python:3.13-alpine
RUN apk add --no-cache bash jq
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY --from=jabridge /out/jabridge /usr/local/bin/jabridge
COPY --from=jabridge /src/LICENSE /usr/share/licenses/jabridge/LICENSE
COPY LICENSE /usr/share/licenses/ha-jabra/LICENSE
COPY docker/entrypoint.sh /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

LABEL org.opencontainers.image.title="ha-jabra (jabra2mqtt)" \
      org.opencontainers.image.description="Jabra headsets in Home Assistant via MQTT" \
      org.opencontainers.image.source="https://github.com/3DJupp/ha-jabra" \
      org.opencontainers.image.licenses="Apache-2.0"
