FROM python:3.12-slim
WORKDIR /app
COPY crm_sync ./crm_sync
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "crm_sync", "serve"]
