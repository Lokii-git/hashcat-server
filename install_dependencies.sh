#!/bin/bash

# Install required dependencies for hashcat-server admin panel
echo "Installing required Python packages for hashcat-server admin panel..."
pip install sqlalchemy passlib[bcrypt] psutil fastapi uvicorn python-multipart --break-system-packages

# Check if installation was successful
if [ $? -eq 0 ]; then
    echo "Dependencies installed successfully."
    
    # Restart the hashcat-server service
    echo "Restarting hashcat-server service..."
    sudo systemctl restart hashcat-server
    
    # Check service status
    echo "Service status:"
    sudo systemctl status hashcat-server | head -n 20
else
    echo "Error installing dependencies. Please check for errors above."
fi
