#!/bin/bash

# Script to monitor Gremlin server container health with exponential backoff

echo "Getting container ID..."
CONTAINER_ID=$(docker ps -q -f "name=gremlin-server")

if [ -z "$CONTAINER_ID" ]; then
    echo "Error: Could not find gremlin-server container"
    exit 1
fi

echo "Found container: $CONTAINER_ID"

MAX_ATTEMPTS=30
ATTEMPT=1
DELAY=2

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    STATUS=$(docker inspect --format="{{if .Config.Healthcheck}}{{print .State.Health.Status}}{{end}}" $CONTAINER_ID)
    
    echo "Health check attempt $ATTEMPT/$MAX_ATTEMPTS: $STATUS"
    
    if [ "$STATUS" = "healthy" ]; then
        echo "Container started successfully"
        # Print server version and configuration
        echo "Gremlin Server Details:"
        curl -s http://localhost:8182/status
        exit 0
    elif [ "$STATUS" = "unhealthy" ]; then
        echo "Container failed to start properly."
        echo "Container logs:"
        docker logs $CONTAINER_ID
        echo "Container health check logs:"
        docker inspect $CONTAINER_ID | jq '.[0].State.Health'
        exit 1
    fi

    echo "Container starting, waiting ${DELAY} seconds..."
    sleep $DELAY
    
    # Exponential backoff with max 32 second delay
    DELAY=$(( DELAY * 2 > 32 ? 32 : DELAY * 2 ))
    ATTEMPT=$((ATTEMPT + 1))
done

echo "Container failed to become healthy after $MAX_ATTEMPTS attempts"
echo "Final container state:"
docker inspect $CONTAINER_ID
echo "Container logs:"
docker logs $CONTAINER_ID
exit 1