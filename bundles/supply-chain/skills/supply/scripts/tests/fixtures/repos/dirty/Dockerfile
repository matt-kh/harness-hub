FROM node:20 AS build
RUN npm ci
FROM alpine
COPY --from=build /app /app
FROM build AS test
FROM scratch
