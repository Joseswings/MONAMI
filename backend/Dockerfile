FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:0.11.18 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --create-home monami
USER monami
EXPOSE 8000
CMD ["python", "-m", "app.serve"]
