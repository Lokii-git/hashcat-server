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

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR] This script must be run as root${NC}"
    exit 1
fi

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}     Hashcat Server - Installation Script         ${NC}"
echo -e "${BLUE}==================================================${NC}"

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

# Create installation directory
echo -e "${GREEN}[INFO] Creating installation directory ${INSTALL_DIR}...${NC}"
mkdir -p ${INSTALL_DIR}
if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR] Failed to create directory ${INSTALL_DIR}${NC}"
    exit 1
fi

# Copy files to installation directory
echo -e "${GREEN}[INFO] Copying files to ${INSTALL_DIR}...${NC}"
cp -r ./* ${INSTALL_DIR}/
if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR] Failed to copy files to ${INSTALL_DIR}${NC}"
    exit 1
fi

# Create necessary directories
echo -e "${GREEN}[INFO] Creating necessary directories...${NC}"
mkdir -p ${INSTALL_DIR}/{uploads,hashes,wordlists,outputs,logs}

# Set proper ownership and permissions
echo -e "${GREEN}[INFO] Setting proper permissions...${NC}"
chown -R ${USER}:${GROUP} ${INSTALL_DIR}
chmod -R 755 ${INSTALL_DIR}

# Ensure directories are writable by the service user
chmod 775 ${INSTALL_DIR}/{uploads,hashes,wordlists,outputs,logs}
chmod 664 ${INSTALL_DIR}/jobs.json 2>/dev/null || true

# Create empty jobs.json file if it doesn't exist
if [ ! -f "${INSTALL_DIR}/jobs.json" ]; then
    echo -e "${GREEN}[INFO] Creating empty jobs.json file...${NC}"
    echo "{}" > ${INSTALL_DIR}/jobs.json
    chown ${USER}:${GROUP} ${INSTALL_DIR}/jobs.json
    chmod 664 ${INSTALL_DIR}/jobs.json
fi

# Install required Python packages
echo -e "${GREEN}[INFO] Installing required Python packages...${NC}"
if [ -f "${INSTALL_DIR}/requirements.txt" ]; then
    pip3 install -r ${INSTALL_DIR}/requirements.txt
    if [ $? -ne 0 ]; then
        echo -e "${RED}[ERROR] Failed to install required Python packages${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}[WARNING] requirements.txt not found${NC}"
fi

# Install systemd service
echo -e "${GREEN}[INFO] Installing systemd service...${NC}"
if [ -f "${INSTALL_DIR}/hashcat-server.service" ]; then
    # Update paths in service file
    sed -i "s|/opt/hashcat-server|${INSTALL_DIR}|g" ${INSTALL_DIR}/hashcat-server.service
    sed -i "s|User=hashcat|User=${USER}|g" ${INSTALL_DIR}/hashcat-server.service
    
    cp ${INSTALL_DIR}/hashcat-server.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    
    echo -e "${GREEN}[SUCCESS] Systemd service installed and enabled${NC}"
    echo -e "${GREEN}[INFO] You can start the service with: systemctl start ${SERVICE_NAME}${NC}"
else
    echo -e "${YELLOW}[WARNING] Service file not found. Skipping systemd setup.${NC}"
fi

echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}[SUCCESS] Installation complete!${NC}"
echo -e "${GREEN}[INFO] Hashcat Server installed to ${INSTALL_DIR}${NC}"
echo -e "${GREEN}[INFO] Control commands:${NC}"
echo -e "${BLUE}  Start:   ${NC}systemctl start ${SERVICE_NAME}"
echo -e "${BLUE}  Stop:    ${NC}systemctl stop ${SERVICE_NAME}"
echo -e "${BLUE}  Status:  ${NC}systemctl status ${SERVICE_NAME}"
echo -e "${BLUE}  Logs:    ${NC}journalctl -u ${SERVICE_NAME}"
echo -e "${BLUE}==================================================${NC}"

# Start the service if requested
read -p "Do you want to start the Hashcat Server now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${GREEN}[INFO] Starting Hashcat Server...${NC}"
    systemctl start ${SERVICE_NAME}
    
    # Check if service started successfully
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        echo -e "${GREEN}[SUCCESS] Hashcat Server started successfully${NC}"
        echo -e "${GREEN}[INFO] You can access the server at http://YOUR_SERVER_IP:8000${NC}"
    else
        echo -e "${RED}[ERROR] Failed to start Hashcat Server${NC}"
        echo -e "${YELLOW}[INFO] Check logs with: journalctl -u ${SERVICE_NAME}${NC}"
    fi
fi

exit 0
