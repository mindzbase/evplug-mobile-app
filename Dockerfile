FROM python:3.9.19-bookworm

WORKDIR /app

COPY requirements.txt requirements.txt
RUN apt-get update && \
    apt-get upgrade -y && \
    apt-get install -y git

RUN pip install --no-cache-dir -r requirements.txt
RUN pip install passlib && \
    pip install boto3 && \
    pip install aiocache && \
    pip install async_firebase

COPY . .

EXPOSE 8080 8765 80

# CMD ["python", "server.py"]