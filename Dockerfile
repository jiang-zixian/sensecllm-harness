FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY helpers ./helpers
COPY sensor_rag ./sensor_rag
COPY scripts ./scripts
COPY examples ./examples

RUN python -m pip install --upgrade pip \
    && python -m pip install -e '.[api,legacy,rag]'

RUN mkdir -p /app/runs /app/.rag_index

EXPOSE 8000

CMD ["uvicorn", "sensecllm.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
