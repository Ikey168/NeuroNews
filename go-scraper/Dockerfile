# NeuroNews Go Scraper Dockerfile
FROM golang:1.21-alpine AS builder

# Install Chrome dependencies
RUN apk add --no-cache \
    chromium \
    ca-certificates \
    tzdata

# Set working directory
WORKDIR /app

# Copy go mod files
COPY go.mod go.sum ./

# Download dependencies
RUN go mod download

# Copy source code
COPY . .

# Build the application
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o neuronews-scraper .

# Production stage
FROM alpine:latest

# Install Chrome and dependencies
RUN apk add --no-cache \
    chromium \
    ca-certificates \
    tzdata \
    && adduser -D -s /bin/sh scraper

# Set Chrome path
ENV CHROME_BIN=/usr/bin/chromium-browser

# Create directories
RUN mkdir -p /app/output /app/config

# Copy binary and config
COPY --from=builder /app/neuronews-scraper /app/
COPY --from=builder /app/config.json /app/config/

# Set ownership
RUN chown -R scraper:scraper /app

# Switch to non-root user
USER scraper

# Set working directory
WORKDIR /app

# Expose volume for output
VOLUME ["/app/output"]

# Default command
CMD ["./neuronews-scraper", "-config", "config/config.json"]
