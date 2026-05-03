FROM rust:1.82-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
ENV SQLX_OFFLINE=true
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs \
    && cargo build --release --bin mcp-analytics \
    && rm -rf src
COPY .sqlx ./.sqlx
COPY src ./src
RUN touch src/main.rs && cargo build --release --bin mcp-analytics

FROM debian:bookworm-slim AS runner
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -r -s /bin/false mcp-analytics
COPY --from=builder /app/target/release/mcp-analytics /usr/local/bin/mcp-analytics
USER mcp-analytics
EXPOSE 9003
CMD ["mcp-analytics"]
