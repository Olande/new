FROM python:3.13-slim

WORKDIR /app


RUN apt-get update && apt-get install -y \
    curl \
    git \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

# Copy the dependency definitions
COPY pyproject.toml uv.lock ./

# Install python dependencies
RUN uv sync --frozen --no-cache

# Copy the rest of the application
COPY . .

# Expose port
EXPOSE 8000

# Set entrypoint
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
