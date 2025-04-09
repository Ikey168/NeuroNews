#!/bin/bash
set -e

# Check if nginx is running
if ! sudo service nginx status > /dev/null; then
    echo "Error: Nginx is not running"
    exit 1
fi

# Check if our application is running under supervisor
if ! sudo supervisorctl status neuronews | grep -q "RUNNING"; then
    echo "Error: Application is not running"
    exit 1
fi

# Wait for application to be ready
sleep 5

# Check if the application is responding
response_code=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health)

if [ "$response_code" != "200" ]; then
    echo "Error: Application health check failed with response code $response_code"
    exit 1
fi

# Check system resources
memory_usage=$(free -m | awk '/Mem:/ { printf("%.2f%%", $3/$2 * 100) }')
disk_usage=$(df -h / | awk 'NR==2 { print $5 }')
cpu_usage=$(top -bn1 | grep "Cpu(s)" | awk '{print $2 + $4}')

echo "System Status:"
echo "Memory Usage: $memory_usage"
echo "Disk Usage: $disk_usage"
echo "CPU Usage: $cpu_usage%"

# Log validation success
echo "$(date): Service validation completed successfully" >> /home/ubuntu/neuronews/logs/validation.log

exit 0