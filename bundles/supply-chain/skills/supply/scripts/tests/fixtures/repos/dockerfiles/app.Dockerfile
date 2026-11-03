FROM ubuntu:latest
ADD https://example.com/tool.tar.gz /opt/
RUN apt-get update \
 && wget https://example.com/agent.deb \
 && dpkg -i agent.deb
