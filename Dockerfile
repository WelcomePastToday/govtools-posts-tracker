FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create a non-root user? Playwright image already has stricter permissions sometimes, 
# but running as root inside container is often easier for simple scripts unless specified otherwise.
# We will run as root for now to avoid permission issues with output directory creation.

CMD ["python", "tracker.py"]
