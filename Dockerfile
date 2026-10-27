FROM python:3.11-slim AS app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt
COPY integrations/ ./integrations/
COPY travel_agent/ ./travel_agent/
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "travel_agent.web:create_web_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
