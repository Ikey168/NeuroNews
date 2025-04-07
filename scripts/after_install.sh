#!/bin/bash
set -e

# Navigate to application directory
cd /home/ubuntu/neuronews

# Install Python dependencies
pip3 install -r requirements.txt

# Set up environment variables
if [ ! -f ".env" ]; then
    echo "AWS_REGION=us-east-1" >> .env
    echo "SCRAPING_ENABLED=true" >> .env
    echo "SENTIMENT_PROVIDER=vader" >> .env
fi

# Set up log directory
mkdir -p /home/ubuntu/neuronews/logs

# Set correct permissions
sudo chown -R ubuntu:ubuntu /home/ubuntu/neuronews
sudo chmod -R 755 /home/ubuntu/neuronews

# Clean up any old Python cache
find . -type d -name "__pycache__" -exec rm -r {} +

# Install system dependencies for the web server
sudo apt-get install -y nginx supervisor

# Configure Nginx if needed
if [ ! -f "/etc/nginx/sites-enabled/neuronews" ]; then
    sudo bash -c 'cat > /etc/nginx/sites-available/neuronews << EOL
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }
}
EOL'
    sudo ln -sf /etc/nginx/sites-available/neuronews /etc/nginx/sites-enabled/
    sudo rm -f /etc/nginx/sites-enabled/default
fi

# Configure Supervisor
sudo bash -c 'cat > /etc/supervisor/conf.d/neuronews.conf << EOL
[program:neuronews]
directory=/home/ubuntu/neuronews
command=gunicorn src.api.app:app -w 4 -b 127.0.0.1:8000
user=ubuntu
autostart=true
autorestart=true
stderr_logfile=/home/ubuntu/neuronews/logs/gunicorn.err.log
stdout_logfile=/home/ubuntu/neuronews/logs/gunicorn.out.log
EOL'

# Install Gunicorn
pip3 install gunicorn

# Reload configurations
sudo supervisorctl reread
sudo supervisorctl update
sudo service nginx restart