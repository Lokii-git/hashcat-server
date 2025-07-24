import os
import json
from datetime import datetime
from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# Import models for database authentication
from models import User, get_db_session

# Load environment variables from .env file
load_dotenv()

# Initialize HTTP Basic auth
security = HTTPBasic()

# Default credentials from environment variables
DEFAULT_USERNAME = os.getenv("HASHCAT_USERNAME", "Hashes")
DEFAULT_PASSWORD = os.getenv("HASHCAT_PASSWORD", "PasstheH@SH!")

def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    """
    Authenticate user using HTTP Basic Auth and return the User object
    """
    db = get_db_session()
    try:
        # Try database authentication first
        user = db.query(User).filter(User.username == credentials.username).first()
        
        if user and user.is_active and user.verify_password(credentials.password):
            # Update last login time
            user.last_login = datetime.utcnow()
            db.commit()
            return user
            
        # Fall back to legacy credential check if no user found or password incorrect
        if not user:
            if os.path.exists("credentials.json"):
                with open("credentials.json", "r") as f:
                    creds = json.load(f)
                legacy_username = creds.get("username", DEFAULT_USERNAME)
                legacy_password = creds.get("password", DEFAULT_PASSWORD)
            else:
                # Use environment variables or defaults
                legacy_username = DEFAULT_USERNAME
                legacy_password = DEFAULT_PASSWORD
                
            if credentials.username == legacy_username and credentials.password == legacy_password:
                # Create user in database from legacy credentials
                new_user = User(
                    username=legacy_username,
                    password_hash=User.get_password_hash(legacy_password),
                    is_admin=True,  # Legacy user is admin
                    is_active=True
                )
                db.add(new_user)
                db.commit()
                return new_user
        
        # Authentication failed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    finally:
        db.close()

def get_current_username(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    Backwards compatibility function for existing code
    """
    db = get_db_session()
    try:
        user = db.query(User).filter(User.username == credentials.username).first()
        if user and user.is_active and user.verify_password(credentials.password):
            return user.username
            
        # Fall back to legacy credential check if needed
        if os.path.exists("credentials.json"):
            with open("credentials.json", "r") as f:
                creds = json.load(f)
            legacy_username = creds.get("username", DEFAULT_USERNAME)
            legacy_password = creds.get("password", DEFAULT_PASSWORD)
        else:
            legacy_username = DEFAULT_USERNAME
            legacy_password = DEFAULT_PASSWORD
            
        if credentials.username == legacy_username and credentials.password == legacy_password:
            return legacy_username
            
        # Authentication failed
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    finally:
        db.close()

def get_admin_user(user = Depends(get_current_user)):
    """
    Check if the current user is an admin
    """
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        )
    return user

def initialize_credentials():
    """
    Initialize credentials file and database if they don't exist
    """
    try:
        # Initialize the database
        from models import init_db
        init_db()
        
        # For backwards compatibility, still maintain credentials.json
        if not os.path.exists("credentials.json"):
            creds = {
                "username": DEFAULT_USERNAME,
                "password": DEFAULT_PASSWORD
            }
            with open("credentials.json", "w") as f:
                json.dump(creds, f)
            print(f"Created default credentials: {DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")
        else:
            # Validate the credentials.json file
            try:
                with open("credentials.json", "r") as f:
                    creds = json.load(f)
                if "username" not in creds or "password" not in creds:
                    print("Warning: credentials.json is missing username or password fields!")
                    print(f"Using default credentials: {DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")
            except json.JSONDecodeError:
                print("Warning: credentials.json is not valid JSON!")
                print(f"Using default credentials: {DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")
            
        # Create .env file if it doesn't exist
        if not os.path.exists(".env"):
            with open(".env", "w") as f:
                f.write(f"HASHCAT_USERNAME={DEFAULT_USERNAME}\n")
                f.write(f"HASHCAT_PASSWORD={DEFAULT_PASSWORD}\n")
    except Exception as e:
        print(f"Error initializing credentials: {str(e)}")
        print(f"Using default credentials: {DEFAULT_USERNAME} / {DEFAULT_PASSWORD}")
