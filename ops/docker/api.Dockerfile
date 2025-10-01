FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# uvicorn reload watches mounted code
CMD ["uvicorn","services.app_server.main:app","--host","0.0.0.0","--port","8000","--reload"]
