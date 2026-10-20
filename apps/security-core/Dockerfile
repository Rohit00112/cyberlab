FROM rust:1.90-bookworm AS builder
WORKDIR /app
COPY Cargo.toml Cargo.lock ./
COPY src ./src
RUN cargo build --release --locked

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 cyberlab
COPY --from=builder /app/target/release/cyberlab-security-core /usr/local/bin/cyberlab-security-core
USER cyberlab
EXPOSE 8081
HEALTHCHECK --interval=10s --timeout=3s --retries=5 CMD curl --fail --silent http://127.0.0.1:8081/ready || exit 1
ENTRYPOINT ["/usr/local/bin/cyberlab-security-core"]
