FROM python:3.11-slim
WORKDIR /researchos
COPY apps/api/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY apps/api ./apps/api
COPY packages ./packages
COPY scripts ./scripts
COPY pyproject.toml ./
ENV PYTHONPATH=/researchos/apps/api
RUN useradd -m researchos && mkdir -p /researchos/.pytest_cache /researchos/test-results && chown researchos:researchos /researchos/.pytest_cache /researchos/test-results
USER researchos
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
