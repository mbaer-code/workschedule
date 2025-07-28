# Use the official Python image as a base image
# Changed from 'buster' to 'bullseye' as buster repositories are no longer directly accessible.
FROM python:3.10-slim-bullseye

# Set the working directory in the container
WORKDIR /app

# Install dependencies
# Copy requirements.txt first to leverage Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application code
COPY . .

# Install wget, which is needed to download the Cloud SQL Proxy
# The -y flag automatically answers yes to prompts
RUN apt-get update && apt-get install -y wget

# Set the Cloud SQL Proxy version.
# Check https://github.com/GoogleCloudPlatform/cloud-sql-proxy/releases for latest
ENV CLOUD_SQL_PROXY_VERSION 1.33.0

# Download and install the Cloud SQL Proxy
# Corrected the environment variable name from CLOUD_SQL_PROXY_PROXY_VERSION to CLOUD_SQL_PROXY_VERSION
RUN wget https://storage.googleapis.com/cloud-sql-proxy/v${CLOUD_SQL_PROXY_VERSION}/cloud-sql-proxy.linux.amd64 -O /usr/local/bin/cloud_sql_proxy && chmod +x /usr/local/bin/cloud_sql_proxy

# Define the entrypoint for the container
# This will run the Cloud SQL Proxy in the background and then start Gunicorn
# Explicitly calling gunicorn as a Python module to ensure it's found.
# The Cloud SQL Proxy listens on a Unix socket by default, which is what Flask/psycopg2 expect
# The INSTANCE_CONNECTION_NAME environment variable is read by the proxy
# The PORT environment variable is automatically provided by Cloud Run
CMD ["sh", "-c", "cloud_sql_proxy -instances=${INSTANCE_CONNECTION_NAME}=unix:/cloudsql & python -m gunicorn --bind 0.0.0.0:${PORT} app:app"]

# Expose the port that the application will listen on
EXPOSE 8080

