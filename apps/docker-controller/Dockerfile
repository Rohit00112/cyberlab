FROM python:3.13-alpine
COPY controller.py /opt/cyberlab/controller.py
COPY healthcheck.py /opt/cyberlab/healthcheck.py
ENV PYTHONUNBUFFERED=1
CMD ["python", "/opt/cyberlab/controller.py"]
