FROM python:3.11-slim

WORKDIR /app

# Установка зависимостей
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копирование файлов приложения
COPY . .

# Создание директорий
RUN mkdir -p app/templates app/static/css app/static/js

# Переменные окружения
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Порт
EXPOSE 5000

# Запуск приложения
CMD ["python", "app.py"]