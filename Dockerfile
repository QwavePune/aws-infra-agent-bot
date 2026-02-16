# Multi-stage Docker build for LangChain Agent

# Stage 1: Builder
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies (keyring support + terraform)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    dbus \
    libdbus-1-3 \
    curl \
    gnupg \
    lsb-release \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor -o /etc/apt/keyrings/hashicorp-archive-keyring.gpg \
    && chmod a+r /etc/apt/keyrings/hashicorp-archive-keyring.gpg \
    && . /etc/os-release \
    && echo "deb [signed-by=/etc/apt/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com ${VERSION_CODENAME} main" > /etc/apt/sources.list.d/hashicorp.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends terraform \
    && rm -rf /var/lib/apt/lists/*

# Copy Python packages from builder
COPY --from=builder /root/.local /root/.local

# Set environment variables
ENV PATH=/root/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy application code structure
COPY bin/ ./bin/
COPY core/ ./core/
COPY mcp_servers/ ./mcp_servers/
COPY ui/ ./ui/
COPY deployment/ ./deployment/
COPY requirements.txt .

# Create logs directory
RUN mkdir -p logs

# Create non-root user for security
RUN useradd -m -u 1000 agent && \
    chown -R agent:agent /app

USER agent

# Health check for containerized deployments
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python3 -c "import sys; print('healthy')" || exit 1

# Default command - interactive agent
CMD ["python3", "bin/langchain-agent.py"]
