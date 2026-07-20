FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY apps/api/app ./app
COPY apps/api/tests ./tests
COPY apps/web/static ./static

EXPOSE 8000
CMD ["python", "-m", "app.main"]
