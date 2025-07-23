#!/bin/bash

# Script to update permissions for hashcat-server to use current user
# Run this script with sudo privileges

# Set color codes for better readability
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[ERROR] This script must be run as root${NC}"
    exit 1
fi

# Get the user who ran sudo (the SUDO_USER environment variable)
if [ -z "$SUDO_USER" ]; then
    echo -e "${RED}[ERROR] SUDO_USER not found. Make sure to run this with sudo.${NC}"
    exit 1
fi

CURRENT_USER=$SUDO_USER
CURRENT_GROUP=$(id -gn $SUDO_USER)
INSTALL_DIR=$(dirname $(readlink -f $0))

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}  Hashcat Server - Permission Update Script       ${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "${GREEN}[INFO] Using current user: $CURRENT_USER:$CURRENT_GROUP${NC}"
echo -e "${GREEN}[INFO] Installation directory: $INSTALL_DIR${NC}"

# Create necessary directories if they don't exist
echo -e "${GREEN}[INFO] Ensuring directories exist...${NC}"
for dir in uploads hashes wordlists outputs logs potfiles; do
    mkdir -p "$INSTALL_DIR/$dir"
    echo -e "${GREEN}[INFO] Created directory: $INSTALL_DIR/$dir${NC}"
done

# Update ownership of all files and directories
echo -e "${GREEN}[INFO] Updating ownership of files and directories...${NC}"
chown -R $CURRENT_USER:$CURRENT_GROUP "$INSTALL_DIR"
echo -e "${GREEN}[INFO] Changed ownership to $CURRENT_USER:$CURRENT_GROUP${NC}"

# Set proper permissions
echo -e "${GREEN}[INFO] Setting proper permissions...${NC}"
chmod -R 755 "$INSTALL_DIR"
chmod -R 775 "$INSTALL_DIR/uploads" "$INSTALL_DIR/hashes" "$INSTALL_DIR/wordlists" "$INSTALL_DIR/outputs" "$INSTALL_DIR/logs" "$INSTALL_DIR/potfiles"

# Ensure jobs.json is writable
if [ -f "$INSTALL_DIR/jobs.json" ]; then
    chmod 664 "$INSTALL_DIR/jobs.json"
    echo -e "${GREEN}[INFO] Set permissions on jobs.json${NC}"
fi

echo -e "${GREEN}[INFO] Permissions updated successfully!${NC}"
echo -e "${BLUE}==================================================${NC}"
echo -e "${YELLOW}Note: If you're running this as a service, you may need to update your service file to run as $CURRENT_USER${NC}"
echo -e "${BLUE}==================================================${NC}"
