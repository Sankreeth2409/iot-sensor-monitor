FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY iot_monitor ./iot_monitor
RUN useradd --create-home app && mkdir /data && chown app /data
USER app
ENTRYPOINT ["python", "-m", "iot_monitor"]
