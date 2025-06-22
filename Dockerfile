FROM --platform=linux/amd64 maprtech/dev-sandbox-container:latest

ENV DEBIAN_FRONTEND=noninteractive
RUN apt update && apt install -y git python3-dev gcc tree

# fix init-script
RUN sed -i '/after cldb /a     sleep 30; echo mapr | maprlogin password -user mapr' /usr/bin/init-script

EXPOSE 9443 8443 3000 3001 2222

COPY . /app
WORKDIR /app

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
RUN echo "export UV_ENV_FILE=.env" >> $HOME/.bashrc
RUN echo "export LD_LIBRARY_PATH=/opt/mapr/lib" >> $HOME/.bashrc
ENV CFLAGS=-I/opt/mapr/include
ENV LDFLAGS=-L/opt/mapr/lib
RUN . $HOME/.local/bin/env && uv add mapr-streams-python
RUN git config --global credential.helper store
