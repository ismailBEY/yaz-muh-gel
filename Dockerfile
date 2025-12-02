FROM python:3.9-slim

# Saat dilimi ayarı (Türkiye saati için)
RUN apt-get update && apt-get install -y tzdata
ENV TZ="Europe/Istanbul"

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY reminder_app.py .

EXPOSE 5000

CMD ["python", "-u", "reminder_app.py"]