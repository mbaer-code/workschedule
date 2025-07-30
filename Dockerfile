# Use the official Python image as a base image
FROM python:3.10-slim-bullseye

# Set the working directory in the container
WORKDIR /app

# Install dependencies
# Copy requirements.txt first to leverage Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Define the entrypoint for the container
# This will simply start your Gunicorn application.
# Cloud Run's built-in Cloud SQL integration will handle the database connection
# via a Unix socket, so the proxy is no longer needed in the container.
# The PORT environment variable is automatically provided by Cloud Run.
CMD python -m gunicorn --bind 0.0.0.0:${PORT} app:app

# Expose the port that the application will listen on
EXPOSE 8080
