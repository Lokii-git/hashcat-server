#!/bin/bash

# Hashcat Server Control Script for Linux
# Created: July 23, 2025
# This script provides extended functionality to start, stop, and manage the Hashcat Server

# Set color codes for better readability
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Default config
PORT=8000
HOST="0.0.0.0"
LOG_DIR="logs"
PID_FILE="/tmp/hashcat_server.pid"
LOG_FILE="hashcat_server.log"
DAEMON_MODE=false

# Print usage info
print_usage() {
    echo -e "${BLUE}Hashcat Server Control Script${NC}"
    echo -e "Usage: $0 [OPTIONS] COMMAND"
    echo -e "\nCommands:"
    echo -e "  start        Start the Hashcat Server"
    echo -e "  stop         Stop a running Hashcat Server"
    echo -e "  status       Check if the server is running"
    echo -e "  restart      Restart the server"
    echo -e "\nOptions:"
    echo -e "  -p, --port PORT      Port to run the server on (default: ${PORT})"
    echo -e "  -h, --host HOST      Host to bind to (default: ${HOST})"
    echo -e "  -d, --daemon         Run in daemon mode"
    echo -e "  --help               Display this help message"
    echo -e "\nExamples:"
    echo -e "  $0 start             Start the server in foreground mode"
    echo -e "  $0 -d start          Start the server as a daemon"
    echo -e "  $0 -p 9000 start     Start the server on port 9000"
    echo -e "  $0 stop              Stop the server"
}

# Check for directory structure and create if needed
setup_environment() {
    echo -e "${GREEN}[INFO] Setting up directory structure...${NC}"
    mkdir -p uploads hashes wordlists outputs ${LOG_DIR}
    
    # Check for requirements.txt
    if [ ! -f "requirements.txt" ]; then
        echo -e "${YELLOW}[WARNING] requirements.txt not found${NC}"
    fi
    
    # Check for main.py
    if [ ! -f "main.py" ]; then
        echo -e "${RED}[ERROR] main.py not found. Make sure you're running this script from the Hashcat Server directory${NC}"
        exit 1
    fi
    
    # Check for Python
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}[ERROR] Python3 is not installed or not in PATH${NC}"
        exit 1
    fi
    
    # Install dependencies
    if [ -f "requirements.txt" ]; then
        echo -e "${GREEN}[INFO] Installing dependencies...${NC}"
        pip3 install -q --disable-pip-version-check --no-cache-dir -r requirements.txt
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}[ERROR] Failed to install dependencies${NC}"
            exit 1
        fi
    fi
}

# Start the server
start_server() {
    echo -e "${BLUE}==================================================${NC}"
    echo -e "${BLUE}          Hashcat Server - Starting                ${NC}"
    echo -e "${BLUE}==================================================${NC}"
    
    setup_environment
    
    # Check if the server is already running
    if [ -f "${PID_FILE}" ]; then
        PID=$(cat "${PID_FILE}")
        if ps -p "${PID}" > /dev/null; then
            echo -e "${RED}[ERROR] Server is already running with PID ${PID}${NC}"
            exit 1
        else
            echo -e "${YELLOW}[WARNING] Found stale PID file. Removing...${NC}"
            rm "${PID_FILE}"
        fi
    fi
    
    # Check Hashcat installation
    if command -v hashcat &> /dev/null; then
        HASHCAT_VERSION=$(hashcat --version | head -n 1)
        echo -e "${GREEN}[INFO] Hashcat detected: ${HASHCAT_VERSION}${NC}"
    else
        echo -e "${YELLOW}[WARNING] Hashcat not found in PATH. Some features may not work.${NC}"
    fi
    
    # Start the server
    echo -e "${GREEN}[INFO] Starting Hashcat Server on ${HOST}:${PORT}...${NC}"
    
    if [ "${DAEMON_MODE}" = true ]; then
        echo -e "${GREEN}[INFO] Running in daemon mode. Logs will be written to ${LOG_DIR}/${LOG_FILE}${NC}"
        nohup python3 main.py --host "${HOST}" --port "${PORT}" > "${LOG_DIR}/${LOG_FILE}" 2>&1 &
        echo $! > "${PID_FILE}"
        echo -e "${GREEN}[SUCCESS] Server started with PID $(cat ${PID_FILE})${NC}"
    else
        echo -e "${GREEN}[INFO] Running in foreground mode${NC}"
        echo -e "${BLUE}==================================================${NC}"
        python3 main.py --host "${HOST}" --port "${PORT}"
        echo -e "${BLUE}==================================================${NC}"
        echo -e "${GREEN}[INFO] Server has been stopped${NC}"
    fi
}

# Stop the server
stop_server() {
    echo -e "${BLUE}==================================================${NC}"
    echo -e "${BLUE}          Hashcat Server - Stopping                ${NC}"
    echo -e "${BLUE}==================================================${NC}"
    
    if [ ! -f "${PID_FILE}" ]; then
        echo -e "${RED}[ERROR] PID file not found. Server is not running or was not started in daemon mode.${NC}"
        exit 1
    fi
    
    PID=$(cat "${PID_FILE}")
    if ps -p "${PID}" > /dev/null; then
        echo -e "${GREEN}[INFO] Stopping server with PID ${PID}...${NC}"
        kill "${PID}"
        sleep 2
        
        if ps -p "${PID}" > /dev/null; then
            echo -e "${YELLOW}[WARNING] Server did not stop gracefully. Forcing termination...${NC}"
            kill -9 "${PID}"
        fi
        
        rm "${PID_FILE}"
        echo -e "${GREEN}[SUCCESS] Server stopped successfully${NC}"
    else
        echo -e "${YELLOW}[WARNING] Server is not running but PID file exists. Cleaning up...${NC}"
        rm "${PID_FILE}"
    fi
}

# Check server status
check_status() {
    echo -e "${BLUE}==================================================${NC}"
    echo -e "${BLUE}          Hashcat Server - Status                  ${NC}"
    echo -e "${BLUE}==================================================${NC}"
    
    if [ ! -f "${PID_FILE}" ]; then
        echo -e "${YELLOW}[INFO] Server is not running (no PID file found)${NC}"
        return 1
    fi
    
    PID=$(cat "${PID_FILE}")
    if ps -p "${PID}" > /dev/null; then
        echo -e "${GREEN}[INFO] Server is running with PID ${PID}${NC}"
        echo -e "${GREEN}[INFO] Server URL: http://${HOST}:${PORT}${NC}"
        return 0
    else
        echo -e "${RED}[ERROR] Server is not running but PID file exists. Consider cleaning up with 'stop' command.${NC}"
        return 1
    fi
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -p|--port)
            PORT="$2"
            shift 2
            ;;
        -h|--host)
            HOST="$2"
            shift 2
            ;;
        -d|--daemon)
            DAEMON_MODE=true
            shift
            ;;
        --help)
            print_usage
            exit 0
            ;;
        start|stop|status|restart)
            COMMAND="$1"
            shift
            ;;
        *)
            echo -e "${RED}[ERROR] Unknown option: $1${NC}"
            print_usage
            exit 1
            ;;
    esac
done

# Execute the command
case ${COMMAND:-help} in
    start)
        start_server
        ;;
    stop)
        stop_server
        ;;
    status)
        check_status
        ;;
    restart)
        stop_server
        sleep 2
        start_server
        ;;
    help|*)
        print_usage
        exit 1
        ;;
esac

exit 0
