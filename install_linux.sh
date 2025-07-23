#!/bin/bash

# Hashcat Server Installation Script
# Created: July 23, 2025
# This script installs the Hashcat Server as a systemd service

# Set color codes for better readability
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default installation directory
INSTALL_DIR="/opt/hashcat-server"
SERVICE_NAME="hashcat-server"
USER="hashcat"
GROUP="hashcat"
PRESERVE_GIT=true  # Default to preserving Git permissions
USE_CURRENT_USER=false  # Default to not using current user

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        --user)
            USER="$2"
            shift
            shift
            ;;
        --group)
            GROUP="$2"
            shift
            shift
            ;;
        --install-dir)
            INSTALL_DIR="$2"
            shift
            shift
            ;;
        --use-current-user)
            USE_CURRENT_USER=true
            shift
            ;;
        *)
            # Unknown option
            shift
            ;;
    esac
done

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR] This script must be run as root${NC}"
    exit 1
fi

# Use current user if requested
if [ "$USE_CURRENT_USER" = true ]; then
    # Get the user who ran sudo (the SUDO_USER environment variable)
    if [ ! -z "$SUDO_USER" ]; then
        USER=$SUDO_USER
        GROUP=$(id -gn $SUDO_USER)
        echo -e "${GREEN}[INFO] Using current user: $USER:$GROUP${NC}"
    else
        echo -e "${YELLOW}[WARNING] SUDO_USER not found, using default user${NC}"
    fi
fi

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}     Hashcat Server - Installation Script         ${NC}"
echo -e "${BLUE}==================================================${NC}"

# Check if this is a reinstallation
IS_REINSTALL=false
if [ -d "${INSTALL_DIR}" ] && [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
    IS_REINSTALL=true
    echo -e "${GREEN}[INFO] Detected existing installation at ${INSTALL_DIR}${NC}"
    echo -e "${GREEN}[INFO] This will update your existing installation${NC}"
    
    # Check for running service
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        echo -e "${YELLOW}[WARNING] The service is currently running${NC}"
        echo -e "${YELLOW}[INFO] The service will be automatically restarted after update${NC}"
    fi
else
    echo -e "${GREEN}[INFO] Performing fresh installation${NC}"
fi

# Check system requirements
echo -e "${GREEN}[INFO] Checking system requirements...${NC}"

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ERROR] Python 3 is not installed${NC}"
    echo -e "${YELLOW}[INFO] Installing Python 3...${NC}"
    apt-get update
    apt-get install -y python3 python3-pip
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to install Python 3${NC}"
        exit 1
    fi
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo -e "${GREEN}[INFO] Python version: ${PYTHON_VERSION}${NC}"

# Check for Hashcat
if ! command -v hashcat &> /dev/null; then
    echo -e "${YELLOW}[WARNING] Hashcat is not installed${NC}"
    echo -e "${YELLOW}[INFO] Installing Hashcat...${NC}"
    apt-get update
    apt-get install -y hashcat
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to install Hashcat. Please install it manually.${NC}"
    fi
else
    HASHCAT_VERSION=$(hashcat --version | head -n 1)
    echo -e "${GREEN}[INFO] Hashcat detected: ${HASHCAT_VERSION}${NC}"
fi

# Create user if it doesn't exist
if ! id -u ${USER} &>/dev/null; then
    echo -e "${GREEN}[INFO] Creating user ${USER}...${NC}"
    useradd -m -s /bin/bash ${USER}
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to create user ${USER}${NC}"
        exit 1
    fi
fi

# Check if we're running from a git repository
IS_GIT_REPO=false
if [ -d ".git" ]; then
    IS_GIT_REPO=true
    echo -e "${GREEN}[INFO] Detected Git repository${NC}"
fi

# Check if the destination is already a Git repository
IS_DEST_GIT_REPO=false
if [ -d "${INSTALL_DIR}/.git" ]; then
    IS_DEST_GIT_REPO=true
    echo -e "${GREEN}[INFO] Destination is already a Git repository${NC}"
fi

# Check if the current directory is already the installation directory
SAME_DIR=false
CURRENT_DIR=$(pwd)
if [ "$CURRENT_DIR" = "$INSTALL_DIR" ]; then
    SAME_DIR=true
    echo -e "${GREEN}[INFO] Already in the installation directory${NC}"
fi

# Create installation directory if it doesn't exist
if [ ! -d "${INSTALL_DIR}" ]; then
    echo -e "${GREEN}[INFO] Creating installation directory ${INSTALL_DIR}...${NC}"
    mkdir -p ${INSTALL_DIR}
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to create directory ${INSTALL_DIR}${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}[INFO] Installation directory already exists${NC}"
fi

# Copy files to installation directory based on context
if [ "$SAME_DIR" = false ]; then
    if [ "$IS_DEST_GIT_REPO" = true ] && [ "$IS_GIT_REPO" = true ]; then
        # Both source and destination are git repos, ask user what to do
        echo -e "${YELLOW}[WARNING] Both source and destination are Git repositories.${NC}"
        read -p "Do you want to (1) Copy all files or (2) Skip copying files? (1/2): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[1]$ ]]; then
            echo -e "${GREEN}[INFO] Copying all files to ${INSTALL_DIR}...${NC}"
            cp -r ./* ${INSTALL_DIR}/
        else
            echo -e "${GREEN}[INFO] Skipping file copy as requested${NC}"
        fi
    else
        # Normal copy operation
        echo -e "${GREEN}[INFO] Copying files to ${INSTALL_DIR}...${NC}"
        cp -r ./* ${INSTALL_DIR}/
        if [ $? -ne 0 ]; then
            echo -e "${RED}[ERROR] Failed to copy files to ${INSTALL_DIR}${NC}"
            exit 1
        fi
    fi
else
    echo -e "${GREEN}[INFO] Skipping file copy as we're already in the installation directory${NC}"
fi

# Create necessary directories if they don't exist
echo -e "${GREEN}[INFO] Creating necessary directories...${NC}"

# Set proper ownership and permissions - but be selective to preserve git functionality
echo -e "${GREEN}[INFO] Setting proper permissions...${NC}"

# Only change ownership of specific directories needed by the service
# This preserves .git directory permissions for the original user
for dir in uploads hashes wordlists outputs logs potfiles; do
    if [ ! -d "${INSTALL_DIR}/${dir}" ]; then
        echo -e "${GREEN}[INFO] Creating directory ${INSTALL_DIR}/${dir}...${NC}"
        mkdir -p ${INSTALL_DIR}/${dir}
    else
        echo -e "${GREEN}[INFO] Directory ${dir} already exists${NC}"
    fi
    
    echo -e "${GREEN}[INFO] Setting ownership for ${INSTALL_DIR}/${dir}...${NC}"
    chown -R ${USER}:${GROUP} ${INSTALL_DIR}/${dir}
    # Give extra permissions to potfiles directory to avoid permission issues
    if [ "${dir}" = "potfiles" ]; then
        echo -e "${GREEN}[INFO] Setting special permissions for potfiles directory...${NC}"
        chmod -R 777 ${INSTALL_DIR}/${dir}
    else
        chmod -R 775 ${INSTALL_DIR}/${dir}
    fi
done

# Initialize potfile with proper permissions
POTFILE="${INSTALL_DIR}/potfiles/hashcat.pot"
echo -e "${GREEN}[INFO] Creating and setting permissions for potfile at ${POTFILE}...${NC}"
touch "${POTFILE}"
chown ${USER}:${GROUP} "${POTFILE}"
chmod 666 "${POTFILE}"  # rw-rw-rw- permission

# Set ownership for specific files needed by the service
for file in main.py job_runner.py auth.py; do
    if [ -f "${INSTALL_DIR}/${file}" ]; then
        echo -e "${GREEN}[INFO] Setting permissions for ${file}...${NC}"
        chown ${USER}:${GROUP} ${INSTALL_DIR}/${file}
        chmod 755 ${INSTALL_DIR}/${file}
    fi
done

# Handle jobs.json specially
echo -e "${GREEN}[INFO] Setting up jobs.json...${NC}"
touch ${INSTALL_DIR}/jobs.json
chown ${USER}:${GROUP} ${INSTALL_DIR}/jobs.json
chmod 664 ${INSTALL_DIR}/jobs.json

# Create empty jobs.json file if it's empty
if [ ! -s "${INSTALL_DIR}/jobs.json" ]; then
    echo -e "${GREEN}[INFO] Creating empty jobs.json file...${NC}"
    echo "{}" > ${INSTALL_DIR}/jobs.json
    chown ${USER}:${GROUP} ${INSTALL_DIR}/jobs.json
    chmod 664 ${INSTALL_DIR}/jobs.json
fi

# Explicitly protect .git directory from permission changes
if [ -d "${INSTALL_DIR}/.git" ]; then
    echo -e "${GREEN}[INFO] Preserving Git repository permissions...${NC}"
    chmod -R 755 ${INSTALL_DIR}/.git
fi

# Install required Python packages
echo -e "${GREEN}[INFO] Installing required Python packages...${NC}"

# Check for pip3 or pip
PIP_CMD="pip3"
if ! command -v pip3 &> /dev/null; then
    if command -v pip &> /dev/null; then
        PIP_CMD="pip"
    else
        echo -e "${YELLOW}[WARNING] pip not found, attempting to install...${NC}"
        apt-get update && apt-get install -y python3-pip
        if [ $? -ne 0 ]; then
            echo -e "${RED}[ERROR] Failed to install pip${NC}"
            exit 1
        fi
    fi
fi

# Check if requirements.txt exists
if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
    echo -e "${GREEN}[INFO] Installing/upgrading Python packages from requirements.txt...${NC}"
    # Use --upgrade to ensure all packages are up to date after a git pull
    $PIP_CMD install --upgrade -r ${INSTALL_DIR}/requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to install required Python packages${NC}"
        echo -e "${YELLOW}[INFO] Attempting to continue anyway...${NC}"
    fi
else
    echo -e "${YELLOW}[WARNING] requirements.txt not found${NC}"
    # Install minimum required packages
    echo -e "${YELLOW}[INFO] Installing minimum required packages...${NC}"
    $PIP_CMD install fastapi uvicorn python-multipart
fi

# Install systemd service
echo -e "${GREEN}[INFO] Installing systemd service...${NC}"
if [ -f "${INSTALL_DIR}/hashcat-server.service" ]; then
    # Check if service already exists
    SERVICE_EXISTS=false
    if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
        SERVICE_EXISTS=true
        echo -e "${GREEN}[INFO] Existing service found. Updating...${NC}"
        # Stop the service if it's running
        if systemctl is-active --quiet ${SERVICE_NAME}; then
            echo -e "${YELLOW}[INFO] Stopping existing service...${NC}"
            systemctl stop ${SERVICE_NAME}
        fi
    fi
    
    # Create a backup of the service file
    if [ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]; then
        cp "/etc/systemd/system/${SERVICE_NAME}.service" "/etc/systemd/system/${SERVICE_NAME}.service.bak"
        echo -e "${GREEN}[INFO] Backed up existing service file to ${SERVICE_NAME}.service.bak${NC}"
    fi
    
    # Update paths and user in service file
    echo -e "${GREEN}[INFO] Configuring service file...${NC}"
    cp ${INSTALL_DIR}/hashcat-server.service ${INSTALL_DIR}/hashcat-server.service.tmp
    sed -i "s|/opt/hashcat-server|${INSTALL_DIR}|g" ${INSTALL_DIR}/hashcat-server.service.tmp
    sed -i "s|User=hashcat|User=${USER}|g" ${INSTALL_DIR}/hashcat-server.service.tmp
    sed -i "s|Group=hashcat|Group=${GROUP}|g" ${INSTALL_DIR}/hashcat-server.service.tmp
    
    # Install the service
    cp ${INSTALL_DIR}/hashcat-server.service.tmp /etc/systemd/system/${SERVICE_NAME}.service
    rm ${INSTALL_DIR}/hashcat-server.service.tmp
    
    # Reload systemd and enable service
    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    
    if [ "$SERVICE_EXISTS" = true ]; then
        echo -e "${GREEN}[SUCCESS] Systemd service updated and enabled${NC}"
    else
        echo -e "${GREEN}[SUCCESS] Systemd service installed and enabled${NC}"
    fi
    echo -e "${GREEN}[INFO] You can start the service with: systemctl start ${SERVICE_NAME}${NC}"
else
    echo -e "${YELLOW}[WARNING] Service file not found. Skipping systemd setup.${NC}"
fi

echo -e "${BLUE}==================================================${NC}"
if [ "$IS_REINSTALL" = true ]; then
    echo -e "${GREEN}[SUCCESS] Reinstallation complete!${NC}"
    echo -e "${GREEN}[INFO] Hashcat Server updated at ${INSTALL_DIR}${NC}"
else
    echo -e "${GREEN}[SUCCESS] Installation complete!${NC}"
    echo -e "${GREEN}[INFO] Hashcat Server installed to ${INSTALL_DIR}${NC}"
fi

echo -e "${GREEN}[INFO] Control commands:${NC}"
echo -e "${BLUE}  Start:   ${NC}systemctl start ${SERVICE_NAME}"
echo -e "${BLUE}  Stop:    ${NC}systemctl stop ${SERVICE_NAME}"
echo -e "${BLUE}  Status:  ${NC}systemctl status ${SERVICE_NAME}"
echo -e "${BLUE}  Logs:    ${NC}journalctl -u ${SERVICE_NAME}"

# Additional information for reinstallation cases
if [ "$IS_REINSTALL" = true ]; then
    echo -e "${BLUE}--------------------------------------------------${NC}"
    echo -e "${GREEN}[INFO] Since this was a reinstallation:${NC}"
    echo -e "${BLUE}  • ${NC}Previous configuration files were preserved"
    echo -e "${BLUE}  • ${NC}A backup of your previous service file was created at:"
    echo -e "    /etc/systemd/system/${SERVICE_NAME}.service.bak"
    
    # If permissions were changed
    if [ "$IS_GIT_REPO" = true ] || [ "$IS_DEST_GIT_REPO" = true ]; then
        echo -e "${BLUE}  • ${NC}Git repository permissions were preserved"
        echo -e "${BLUE}  • ${NC}You can continue to use git commands normally"
    fi
fi
echo -e "${BLUE}==================================================${NC}"

# Check if service was already running before we started
WAS_ACTIVE=false
if systemctl is-enabled --quiet ${SERVICE_NAME} && systemctl is-active --quiet ${SERVICE_NAME}; then
    WAS_ACTIVE=true
fi

# If this is a reinstall and service was already running, automatically restart it
if [ "$WAS_ACTIVE" = true ]; then
    echo -e "${GREEN}[INFO] Service was previously running. Restarting automatically...${NC}"
    systemctl restart ${SERVICE_NAME}
    
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        echo -e "${GREEN}[SUCCESS] Hashcat Server restarted successfully${NC}"
    else
        echo -e "${RED}[ERROR] Failed to restart Hashcat Server${NC}"
        echo -e "${YELLOW}[INFO] Check logs with: journalctl -u ${SERVICE_NAME} -n 50${NC}"
    fi
else
    # Otherwise ask if user wants to start it
    read -p "Do you want to start the Hashcat Server now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${GREEN}[INFO] Starting Hashcat Server...${NC}"
        systemctl start ${SERVICE_NAME}
        
        # Check if service started successfully
        if systemctl is-active --quiet ${SERVICE_NAME}; then
            echo -e "${GREEN}[SUCCESS] Hashcat Server started successfully${NC}"
            
            # Get server IP for display purposes
            SERVER_IP=$(hostname -I | awk '{print $1}')
            if [ -z "$SERVER_IP" ]; then
                SERVER_IP="YOUR_SERVER_IP"
            fi
            
            echo -e "${GREEN}[INFO] You can access the server at http://${SERVER_IP}:8000${NC}"
        else
            echo -e "${RED}[ERROR] Failed to start Hashcat Server${NC}"
            echo -e "${YELLOW}[INFO] Check logs with: journalctl -u ${SERVICE_NAME} -n 50${NC}"
        fi
    fi
fi

exit 0
