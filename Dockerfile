FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package*.json ./
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY frontend/ .
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 radar
COPY radar radar
COPY schemas schemas
COPY migrations migrations
COPY alembic.ini .
COPY --from=frontend /ui/dist frontend/dist
USER radar
CMD ["uvicorn", "radar.app:app", "--host", "0.0.0.0", "--port", "8000"]

