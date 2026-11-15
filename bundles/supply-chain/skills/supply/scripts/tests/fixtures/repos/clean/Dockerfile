# syntax=docker/dockerfile:1
FROM python:3.12-slim@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef AS build
RUN curl -fsSLo tool.tgz https://example.com/tool-1.2.3.tgz \
 && echo "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef  tool.tgz" | sha256sum -c -
FROM build AS test
FROM scratch
COPY --from=build /app /app
