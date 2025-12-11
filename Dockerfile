# Use Python image
FROM python:3.9-slim

# Install Tesseract OCR engine, English data, and dependencies
RUN apt-get update && \
    apt-get install -y tesseract-ocr tesseract-ocr-eng libtesseract-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python Dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Application Code
COPY . .

# Create a non-root user and switch to it
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Expose Port
EXPOSE 8080

# Start the Application
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]