import os
import json
import secrets
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Initialize HTTP Basic auth
security = HTTPBasic()

# Default credentials from environment variables
DEFAULT_USERNAME = os.getenv("HASHCAT_USERNAME", "admin")
DEFAULT_PASSWORD = os.getenv("HASHCAT_PASSWORD", "password")

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Authenticate user using HTTP Basic Auth
    """
    # Check if we have a credentials file
    if os.path.exists("credentials.json"):
        with open("credentials.json", "r") as f:
            creds = json.load(f)
        correct_username = creds.get("username", DEFAULT_USERNAME)
        correct_password = creds.get("password", DEFAULT_PASSWORD)
    else:
        # Use environment variables or defaults
        correct_username = DEFAULT_USERNAME
        correct_password = DEFAULT_PASSWORD
    
    # Create constant-time comparison function to avoid timing attacks
    is_username_correct = secrets.compare_digest(credentials.username, correct_username)
    is_password_correct = secrets.compare_digest(credentials.password, correct_password)
    
    if not (is_username_correct and is_password_correct):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    
    return credentials.username

def initialize_credentials():
    """
    Initialize credentials file if it doesn't exist
    """
    if not os.path.exists("credentials.json"):
        creds = {
            "username": DEFAULT_USERNAME,
            "password": DEFAULT_PASSWORD
        }
        with open("credentials.json", "w") as f:
            json.dump(creds, f)
        print(f"Created default credentials: {DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")
    
    # Create .env file if it doesn't exist
    if not os.path.exists(".env"):
        with open(".env", "w") as f:
            f.write(f"HASHCAT_USERNAME={DEFAULT_USERNAME}\n")
            f.write(f"HASHCAT_PASSWORD={DEFAULT_PASSWORD}\n")
