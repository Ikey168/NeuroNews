#!/bin/bash

# Script to monitor Gremlin server container health using WebSocket check

echo "Looking for Gremlin server container..."
# Try multiple possible container name patterns
CONTAINER_ID=$(docker ps -q -f "ancestor=tinkerpop/gremlin-server:3.6.2" || \
               docker ps -q -f "name=gremlin-server" || \
               docker ps -q -f "name=*_gremlin-server_*")

if [ -z "$CONTAINER_ID" ]; then
    echo "Error: Could not find Gremlin server container. Current containers:"
    docker ps -a
    echo "Docker container list output:"
    docker container ls -a
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
import time

def check_connection():
    try:
        c = client.Client('ws://localhost:8182/gremlin', 'g')
        result = c.submit('g.V().count()').all().result()
        print(f"Connection successful, vertex count: {result[0]}")
        c.close()
        return True
    except Exception as e:
        print(f"Connection failed: {str(e)}")
        return False

# Try multiple times in case the server is still starting up
for i in range(3):
    if check_connection():
        sys.exit(0)
    time.sleep(2)
sys.exit(1)
EOF

while [ $ATTEMPT -le $MAX_ATTEMPTS ]; do
    echo "Health check attempt $ATTEMPT/$MAX_ATTEMPTS"
    
    # Check if container is running
    CONTAINER_STATE=$(docker inspect -f '{{.State.Status}}' $CONTAINER_ID)
    echo "Container state: $CONTAINER_STATE"
    
    if [ "$CONTAINER_STATE" != "running" ]; then
        echo "Container is not running. Container logs:"
        docker logs $CONTAINER_ID
        exit 1
    fi

    # Check container logs for initialization
    if docker logs $CONTAINER_ID 2>&1 | grep -q "Channel started at port 8182"; then
        echo "Gremlin Server has started, checking connectivity..."
        
        # Try WebSocket connection
        if python3 check_gremlin.py; then
            echo "Gremlin Server is healthy"
            rm check_gremlin.py
            exit 0
        fi
    else
        echo "Waiting for Gremlin Server to initialize..."
    fi

    echo "Server not ready, waiting ${DELAY} seconds..."
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
rm check_gremlin.py
exit 1