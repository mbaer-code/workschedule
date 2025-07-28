# Use the official Python image as a base image
FROM python:3.10-slim-buster

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

# Download and install the Cloud SQL Proxy
# Use the latest stable version for your architecture (linux amd64 is common for Cloud Run)
ENV CLOUD_SQL_PROXY_VERSION 1.33.0 # Check https://github.com/GoogleCloudPlatform/cloud-sql-proxy/releases for latest
RUN wget https://storage.googleapis.com/cloud-sql-proxy/v${CLOUD_SQL_PROXY_PROXY_VERSION}/cloud-sql-proxy.linux.amd64 -O /usr/local/bin/cloud_sql_proxy \
    && chmod +x /usr/local/bin/cloud_sql_proxy

# Define the entrypoint for the container
# This will run the Cloud SQL Proxy in the background and then start Gunicorn
# The Cloud SQL Proxy listens on a Unix socket by default, which is what Flask/psycopg2 expect
# The INSTANCE_CONNECTION_NAME environment variable is read by the proxy
# The PORT environment variable is automatically provided by Cloud Run
CMD ["sh", "-c", "cloud_sql_proxy -instances=${INSTANCE_CONNECTION_NAME}=unix:/cloudsql & gunicorn --bind 0.0.0.0:${PORT} app:app"]

# Expose the port that the application will listen on
EXPOSE 8080

