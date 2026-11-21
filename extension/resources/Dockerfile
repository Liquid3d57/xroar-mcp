FROM debian:12-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential autoconf automake libtool pkg-config texinfo patch ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY build/ ./build/
COPY xroar/ ./xroar/
COPY lwasm/ ./lwasm/
COPY tools/ ./tools/

RUN bash build/build-linux.sh headless

FROM debian:12-slim AS runtime

WORKDIR /app
COPY --from=builder /app/bin/xroar-dev /app/bin/xroar-dev
COPY mcp-server/server.py /app/mcp-server/server.py
COPY config.ini /app/config.ini

RUN apt-get update && apt-get install -y --no-install-recommends python3 strings \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8000
ENV MCP_HOST=0.0.0.0 MCP_PORT=8000
CMD ["python3", "mcp-server/server.py"]
