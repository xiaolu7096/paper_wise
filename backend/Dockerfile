FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PAPERWISE_DATA_DIR=/app/data

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations

ARG PYPI_INDEX_URL=https://pypi.org/simple
ARG PYTORCH_INDEX_URL=https://download.pytorch.org/whl/cpu
ARG PYTORCH_VERSION=2.13.0+cpu

RUN pip install --no-cache-dir \
        --index-url "${PYTORCH_INDEX_URL}" \
        "torch==${PYTORCH_VERSION}" \
    && pip install --no-cache-dir \
        --index-url "${PYPI_INDEX_URL}" \
        ".[retrieval]"

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
