# Imagen mínima de Python para correr el monitor (FastAPI + loop asyncio).
FROM python:3.12-slim

# No generar .pyc y forzar logs sin buffer (se ven en flyctl logs al instante).
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Instalar dependencias primero para aprovechar la cache de capas.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto.
COPY . .

# El dashboard escucha en este puerto (main.py lee PORT; default 8000).
EXPOSE 8000

CMD ["python", "main.py"]
