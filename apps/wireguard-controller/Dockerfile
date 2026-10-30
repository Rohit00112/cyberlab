FROM alpine:3.21
RUN apk add --no-cache python3 wireguard-tools
COPY controller.py /opt/cyberlab/controller.py
CMD ["python3", "/opt/cyberlab/controller.py"]
