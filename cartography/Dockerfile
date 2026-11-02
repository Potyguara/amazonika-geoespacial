FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 QT_QPA_PLATFORM=offscreen HOME=/tmp
RUN apt-get update && apt-get install -y --no-install-recommends python3-qgis qgis-providers python3-pyqt5 fonts-dejavu-core ca-certificates && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY worker.py /srv/worker.py
COPY smoke.py /srv/smoke.py
USER 65534:65534
EXPOSE 8090
CMD ["/usr/bin/python3", "/srv/worker.py"]
