FROM rust:1.82-slim AS builder
WORKDIR /app
RUN apt-get update && apt-get install -y pkg-config libssl-dev && rm -rf /var/lib/apt/lists/*
COPY Cargo.toml Cargo.lock* ./
RUN mkdir src && echo "fn main() {}" > src/main.rs \
    && cargo build --release --bin mcp-crm \
    && rm -rf src
COPY src ./src
RUN touch src/main.rs && cargo build --release --bin mcp-crm

FROM debian:bookworm-slim AS runner
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -r -s /bin/false mcp-crm
COPY --from=builder /app/target/release/mcp-crm /usr/local/bin/mcp-crm
USER mcp-crm
EXPOSE 9001
CMD ["mcp-crm"]
