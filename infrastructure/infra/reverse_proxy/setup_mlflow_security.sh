#!/bin/bash
# MLflow Security Setup Script (Issue #226)
# 
# This script sets up basic security for MLflow development environments
# including nginx reverse proxy with basic authentication.

set -e

# Configuration
NGINX_AUTH_DIR="/etc/nginx/auth"
NGINX_SITES_DIR="/etc/nginx/sites-available"
NGINX_ENABLED_DIR="/etc/nginx/sites-enabled"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_error "This script should not be run as root"
        log_info "Run without sudo, it will prompt for password when needed"
        exit 1
    fi
}

# Check if required tools are installed
check_dependencies() {
    log_info "Checking dependencies..."
    
    local missing_deps=()
    
    if ! command -v nginx &> /dev/null; then
        missing_deps+=("nginx")
    fi
    
    if ! command -v htpasswd &> /dev/null; then
        missing_deps+=("apache2-utils")
    fi
    
    if [[ ${#missing_deps[@]} -gt 0 ]]; then
        log_error "Missing dependencies: ${missing_deps[*]}"
        log_info "Install them with:"
        
        if command -v apt &> /dev/null; then
            echo "sudo apt update && sudo apt install ${missing_deps[*]}"
        elif command -v yum &> /dev/null; then
            echo "sudo yum install nginx httpd-tools"
        elif command -v brew &> /dev/null; then
            echo "brew install nginx"
        else
            echo "Please install nginx and apache2-utils/httpd-tools for your system"
        fi
        
        exit 1
    fi
    
    log_info "All dependencies are installed"
}

# Create nginx auth directory
setup_auth_directory() {
    log_info "Setting up authentication directory..."
    
    if [[ ! -d "$NGINX_AUTH_DIR" ]]; then
        sudo mkdir -p "$NGINX_AUTH_DIR"
        log_info "Created $NGINX_AUTH_DIR"
    else
        log_info "Auth directory already exists"
    fi
}

# Create basic auth users
create_auth_users() {
    log_info "Setting up basic authentication users..."
    
    local auth_file="$NGINX_AUTH_DIR/mlflow.htpasswd"
    local create_new_file=true
    
    if [[ -f "$auth_file" ]]; then
        echo -n "Auth file already exists. Do you want to recreate it? (y/n): "
        read -r response
        if [[ "$response" != "y" && "$response" != "Y" ]]; then
            create_new_file=false
            log_info "Keeping existing auth file"
        fi
    fi
    
    if [[ "$create_new_file" == "true" ]]; then
        echo -n "Enter username for MLflow access: "
        read -r username
        
        if [[ -z "$username" ]]; then
            log_error "Username cannot be empty"
            exit 1
        fi
        
        # Create or recreate the auth file
        sudo htpasswd -c "$auth_file" "$username"
        log_info "Created auth file with user: $username"
    fi
    
    # Option to add more users
    while true; do
        echo -n "Do you want to add another user? (y/n): "
        read -r response
        if [[ "$response" != "y" && "$response" != "Y" ]]; then
            break
        fi
        
        echo -n "Enter additional username: "
        read -r username
        
        if [[ -n "$username" ]]; then
            sudo htpasswd "$auth_file" "$username"
            log_info "Added user: $username"
        fi
    done
}

# Install nginx configuration
install_nginx_config() {
    log_info "Installing nginx configuration..."
    
    local config_source="$PROJECT_ROOT/infra/reverse_proxy/mlflow-nginx.conf"
    local config_dest="$NGINX_SITES_DIR/mlflow"
    local enabled_link="$NGINX_ENABLED_DIR/mlflow"
    
    if [[ ! -f "$config_source" ]]; then
        log_error "Configuration file not found: $config_source"
        exit 1
    fi
    
    # Copy configuration
    sudo cp "$config_source" "$config_dest"
    log_info "Copied configuration to $config_dest"
    
    # Enable site
    if [[ ! -L "$enabled_link" ]]; then
        sudo ln -s "$config_dest" "$enabled_link"
        log_info "Enabled MLflow site"
    else
        log_info "MLflow site already enabled"
    fi
    
    # Test configuration
    log_info "Testing nginx configuration..."
    if sudo nginx -t; then
        log_info "Nginx configuration is valid"
    else
        log_error "Nginx configuration test failed"
        exit 1
    fi
}

# Restart nginx service
restart_nginx() {
    log_info "Restarting nginx..."
    
    if sudo systemctl restart nginx; then
        log_info "Nginx restarted successfully"
    else
        log_error "Failed to restart nginx"
        exit 1
    fi
    
    # Check if nginx is running
    if sudo systemctl is-active --quiet nginx; then
        log_info "Nginx is running"
    else
        log_error "Nginx is not running"
        exit 1
    fi
}

# Create MLflow startup script
create_mlflow_script() {
    log_info "Creating MLflow startup script..."
    
    local script_path="$PROJECT_ROOT/start_mlflow_secure.sh"
    
    cat > "$script_path" << 'EOF'
#!/bin/bash
# MLflow Secure Startup Script
# Starts MLflow server on localhost only for reverse proxy access

# Configuration
MLFLOW_HOST="127.0.0.1"
MLFLOW_PORT="5000"
MLFLOW_BACKEND_STORE_URI="${MLFLOW_BACKEND_STORE_URI:-sqlite:///mlflow.db}"
MLFLOW_ARTIFACT_ROOT="${MLFLOW_ARTIFACT_ROOT:-./mlruns}"

echo "Starting MLflow server..."
echo "Host: $MLFLOW_HOST"
echo "Port: $MLFLOW_PORT"
echo "Backend Store: $MLFLOW_BACKEND_STORE_URI"
echo "Artifact Root: $MLFLOW_ARTIFACT_ROOT"
echo ""
echo "Access MLflow through nginx proxy at: http://localhost:8080/mlflow/"
echo ""

mlflow server \
    --host "$MLFLOW_HOST" \
    --port "$MLFLOW_PORT" \
    --backend-store-uri "$MLFLOW_BACKEND_STORE_URI" \
    --default-artifact-root "$MLFLOW_ARTIFACT_ROOT" \
    --serve-artifacts
EOF
    
    chmod +x "$script_path"
    log_info "Created MLflow startup script: $script_path"
}

# Display setup information
show_setup_info() {
    log_info "Setup completed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Start MLflow server:"
    echo "   ./start_mlflow_secure.sh"
    echo ""
    echo "2. Access MLflow through proxy:"
    echo "   URL: http://localhost:8080/mlflow/"
    echo "   Authentication: Use the username/password you created"
    echo ""
    echo "3. Check nginx status:"
    echo "   sudo systemctl status nginx"
    echo ""
    echo "4. View nginx logs:"
    echo "   sudo tail -f /var/log/nginx/mlflow-access.log"
    echo "   sudo tail -f /var/log/nginx/mlflow-error.log"
    echo ""
    echo "Configuration files:"
    echo "- Nginx config: $NGINX_SITES_DIR/mlflow"
    echo "- Auth file: $NGINX_AUTH_DIR/mlflow.htpasswd"
    echo "- MLflow script: $PROJECT_ROOT/start_mlflow_secure.sh"
    echo ""
    echo "To add more users later:"
    echo "sudo htpasswd $NGINX_AUTH_DIR/mlflow.htpasswd username"
}

# Main setup function
main() {
    echo "=============================================="
    echo "MLflow Security Setup (Issue #226)"
    echo "=============================================="
    
    check_root
    check_dependencies
    setup_auth_directory
    create_auth_users
    install_nginx_config
    restart_nginx
    create_mlflow_script
    show_setup_info
}

# Run main function
main "$@"
