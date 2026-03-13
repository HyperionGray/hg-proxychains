FROM python:3.11-slim
RUN pip install --no-cache-dir pproxy
EXPOSE 3128
CMD ["pproxy", "-l", "http://0.0.0.0:3128"]
