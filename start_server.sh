#!/bin/bash

# Hashcat Server Startup Script for Linux
# Created: July 23, 2025

# Set color codes for better readability
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}          Hashcat Server - Startup Script          ${NC}"
echo -e "${BLUE}==================================================${NC}"

# Check if running with sufficient permissions
if [ "$EUID" -eq 0 ]; then
  echo -e "${YELLOW}[WARNING] Running as root is not recommended${NC}"
fi

# Check Python version
echo -e "${GREEN}[INFO] Checking Python version...${NC}"
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')

if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR] Python3 is not installed or not in PATH${NC}"
    exit 1
fi

echo -e "${GREEN}[INFO] Python version: ${PYTHON_VERSION}${NC}"

# Create directories if they don't exist
echo -e "${GREEN}[INFO] Setting up directory structure...${NC}"
mkdir -p uploads hashes wordlists outputs

# Check for required packages
echo -e "${GREEN}[INFO] Checking dependencies...${NC}"
pip3 install -q --disable-pip-version-check --no-cache-dir -r requirements.txt

if [ $? -ne 0 ]; then
    echo -e "${RED}[ERROR] Failed to install dependencies${NC}"
    echo -e "${YELLOW}[INFO] Try running: pip3 install -r requirements.txt${NC}"
    exit 1
fi

# Check if Hashcat is installed
echo -e "${GREEN}[INFO] Checking for Hashcat...${NC}"
if command -v hashcat &> /dev/null; then
    HASHCAT_VERSION=$(hashcat --version | head -n 1)
    echo -e "${GREEN}[INFO] Hashcat detected: ${HASHCAT_VERSION}${NC}"
else
    echo -e "${YELLOW}[WARNING] Hashcat not found in PATH${NC}"
    echo -e "${YELLOW}[WARNING] You may need to install Hashcat or add it to your PATH${NC}"
fi

# Check if port is in use
PORT=8000
echo -e "${GREEN}[INFO] Checking if port ${PORT} is available...${NC}"
if netstat -tuln | grep -q ":${PORT} "; then
    echo -e "${RED}[ERROR] Port ${PORT} is already in use${NC}"
    echo -e "${YELLOW}[INFO] You can modify the port in main.py if needed${NC}"
    exit 1
fi

# Start the server
echo -e "${GREEN}[INFO] Starting Hashcat Server...${NC}"
echo -e "${BLUE}==================================================${NC}"
python3 main.py

# If the server exits, show message
echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}[INFO] Hashcat Server has been stopped${NC}"
