FROM --platform=linux/amd64 maprtech/dev-sandbox-container:latest

RUN apt update && apt install -y git python3-dev gcc

ENV clusterName=maprdemo.io
ENV isSecure=true
ENV MAPR_TZ=Europe/London
ENV LD_LIBRARY_PATH=/opt/mapr/lib
ENV CFLAGS=-I/opt/mapr/include
ENV LDFLAGS=-L/opt/mapr/lib

EXPOSE 8443 3000 3001 2222

COPY . /app
WORKDIR /app
RUN mkdir -p images; tar -xf ./downloaded_images.tar -C images/

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN . $HOME/.local/bin/env && uv add mapr-streams-python

# CMD ["./LD_LIBRARY_PATH=/opt/mapr/lib uv run hq.py"]
