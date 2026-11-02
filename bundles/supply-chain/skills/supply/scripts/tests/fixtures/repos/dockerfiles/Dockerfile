ARG BASE=debian:12
FROM ${BASE} AS base
FROM --platform=$BUILDPLATFORM golang:1.23@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef AS build
RUN go build -o app ./cmd/app
FROM build AS test
FROM gcr.io/distroless/static:nonroot
ADD --checksum=sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef https://example.com/ca.tar.gz /ca/
COPY --from=build /src/app /app
FROM scratch
