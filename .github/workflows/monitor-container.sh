#!/bin/bash

# Script to monitor Gremlin server container health using WebSocket check

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

# Install required packages
echo "Installing dependencies..."
apt-get update > /dev/null
apt-get install -y netcat python3 python3-pip > /dev/null
pip3 install gremlinpython --quiet

# Create a Python script for WebSocket health check
cat > check_gremlin.py << 'EOF'
from gremlin_python.driver import client
import sys

try:
    c = client.Client('ws://localhost:8182/gremlin', 'g')
    result = c.submit('g.V().count()').all().result()
    print(f"Connection successful, vertex count: {result[0]}")
    c.close()
    sys.exit(0)
except Exception as e:
    print(f"Connection failed: {str(e)}")
    sys.exit(1)
EOF

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    echo "Health check attempt $ATTEMPT/$MAX_ATTEMPTS"
    
    # Check if container is running
    if [ "$(docker inspect -f '{{.State.Running}}' $CONTAINER_ID)" != "true" ]; then
        echo "Container is not running:"
        docker logs $CONTAINER_ID
        exit 1
    fi

    # Try WebSocket connection
    if python3 check_gremlin.py; then
        echo "Gremlin Server is healthy"
        rm check_gremlin.py
        exit 0
    fi

    echo "Server not ready, waiting ${DELAY} seconds..."
    sleep $DELAY
    
    # Exponential backoff with max 32 second delay
    DELAY=$(( DELAY * 2 > 32 ? 32 : DELAY * 2 ))
    ATTEMPT=$((ATTEMPT + 1))
done

echo "Container failed to become healthy after $MAX_ATTEMPTS attempts"
echo "Container logs:"
docker logs $CONTAINER_ID
echo "Container state:"
docker inspect $CONTAINER_ID | jq '.[0].State'
rm check_gremlin.py
exit 1