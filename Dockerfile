FROM python:3.14-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create directories
RUN mkdir -p app/templates app/static/css app/static/js

# Environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Port
EXPOSE 5000

# Run application
CMD ["python", "app.py"]