
# Use the official Python image as a base image
FROM python:3.10-slim-bullseye

# Set the working directory in the container
WORKDIR /app

# Install dependencies
# Copy requirements.txt first to leverage Docker caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
# This single command copies everything from your project's root
# into the /app directory in the container, including
# instance/service-account.json

COPY . .

COPY instance/service-account.json /instance/service-account.json

# Force unbuffered Python output so print() and logging appear immediately in Cloud Run logs
ENV PYTHONUNBUFFERED=1

# Define the entrypoint for the container
CMD python -m gunicorn --bind 0.0.0.0:${PORT} workschedule.wsgi:app

# Expose the port that the application will listen on
EXPOSE 8080
