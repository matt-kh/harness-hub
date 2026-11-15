FROM alpine:3.20@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef AS alpinebuild
RUN apk add --no-cache ca-certificates \
# a comment line inside the continuation is skipped, not a line end
 && curl -fsSL https://example.com/install.sh | sh
FROM alpinebuild
