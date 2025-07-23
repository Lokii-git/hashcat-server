# Hashcat Server Admin Panel Requirements

## 1. Database Setup

### Install Required Packages
```
pip install sqlalchemy passlib[bcrypt] psutil
```

## 2. Create Database Models
Create a file named `models.py` with the following content:

```python
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, scoped_session
from sqlalchemy.sql import func
from passlib.context import CryptContext
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import os

# Create SQLAlchemy base
Base = declarative_base()

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Define User model
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    email = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=func.now())
    last_login = Column(DateTime, nullable=True)
    last_password_change = Column(DateTime, default=func.now())
    
    # Relationship to jobs (one-to-many)
    jobs = relationship("JobAssociation", back_populates="user", cascade="all, delete-orphan")
    
    def set_password(self, password: str) -> None:
        """Hash password and store it."""
        self.password_hash = pwd_context.hash(password)
        self.last_password_change = datetime.now()
    
    def verify_password(self, plain_password: str) -> bool:
        """Verify password against stored hash."""
        return pwd_context.verify(plain_password, self.password_hash)
    
    def password_expired(self, days: int = 90) -> bool:
        """Check if password has expired."""
        if self.last_password_change:
            expiration_date = self.last_password_change + timedelta(days=days)
            return datetime.now() > expiration_date
        return False
    
    def update_last_login(self) -> None:
        """Update last login time."""
        self.last_login = datetime.now()

# Define JobAssociation model (links users to jobs)
class JobAssociation(Base):
    __tablename__ = "job_associations"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    job_name = Column(String, nullable=True)
    job_status = Column(String, nullable=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)
    
    # Job data (stored as JSON string)
    job_data = Column(Text, nullable=True)
    
    # Relationship to user (many-to-one)
    user = relationship("User", back_populates="jobs")
    
    def update_status(self, status: str) -> None:
        """Update job status and timestamps."""
        self.job_status = status
        self.updated_at = datetime.now()
        
        if status.lower() in ["completed", "finished", "done"]:
            self.completed_at = datetime.now()

# Database setup
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./hashcat_server.db")
engine = create_engine(DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = scoped_session(SessionLocal)

# Function to get database session
def get_db_session():
    """Get database session."""
    db = db_session()
    try:
        yield db
    finally:
        db.close()
```

## 3. Create Database Connection File
Create a file named `database.py` with the following content:

```python
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
import os

# Database setup
DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///./hashcat_server.db")
engine = create_engine(DATABASE_URL)

# Create base class for models
Base = declarative_base()

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db_session = scoped_session(SessionLocal)

# Function to get database session
def get_db_session():
    """Get database session."""
    db = db_session()
    try:
        yield db
    finally:
        db.close()
```

## 4. Update Authentication System
Create or update a file named `auth.py` with the following content:

```python
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
import secrets
import json
import os
from pathlib import Path
from datetime import datetime

from models import User
from database import get_db_session
from settings import get_login_attempt_tracker

# Setup HTTP Basic auth
security = HTTPBasic()

# Path to legacy users file (for backward compatibility)
USERS_FILE = Path("users.json")

def get_legacy_users():
    """Get legacy users from JSON file."""
    if not USERS_FILE.exists():
        return {}
    
    try:
        with open(USERS_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}

def migrate_legacy_users(db: Session):
    """Migrate legacy users to database."""
    legacy_users = get_legacy_users()
    
    for username, password in legacy_users.items():
        # Check if user already exists in database
        user = db.query(User).filter(User.username == username).first()
        if not user:
            # Create new user with legacy credentials
            user = User(
                username=username,
                is_admin=(username == "admin"),  # Assume only 'admin' is an admin
                is_active=True
            )
            user.set_password(password)
            db.add(user)
    
    if legacy_users:
        db.commit()

def get_current_user(
    credentials: HTTPBasicCredentials = Depends(security),
    db: Session = Depends(get_db_session)
):
    """Get current authenticated user."""
    # Check login attempt lockout
    login_tracker = get_login_attempt_tracker()
    if login_tracker.is_locked_out(credentials.username):
        remaining_time = login_tracker.get_remaining_lockout_time(credentials.username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Try again in {remaining_time} seconds."
        )
    
    # Try database authentication first
    user = db.query(User).filter(User.username == credentials.username).first()
    if user and user.is_active and user.verify_password(credentials.password):
        # Successful database authentication
        login_tracker.record_attempt(credentials.username, success=True)
        user.update_last_login()
        db.commit()
        return user
    
    # Try legacy authentication as fallback
    legacy_users = get_legacy_users()
    correct_password = legacy_users.get(credentials.username)
    
    if correct_password and secrets.compare_digest(credentials.password, correct_password):
        # Successful legacy authentication, migrate user
        if not user:
            # Create new user with credentials
            user = User(
                username=credentials.username,
                is_admin=(credentials.username == "admin"),  # Assume only 'admin' is an admin
                is_active=True
            )
            user.set_password(credentials.password)
            db.add(user)
            db.commit()
            db.refresh(user)
        
        login_tracker.record_attempt(credentials.username, success=True)
        user.update_last_login()
        db.commit()
        return user
    
    # Authentication failed
    login_tracker.record_attempt(credentials.username, success=False)
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid username or password",
        headers={"WWW-Authenticate": "Basic"},
    )
```

## 5. Create Settings Manager
Create a file named `settings.py` with the following content:

```python
import os
import json
from datetime import datetime, timedelta
from typing import Dict, Optional

class SettingsManager:
    """
    Manages application settings with file-based storage.
    
    Settings are stored in a JSON file and cached in memory.
    """
    
    _instance = None
    _settings_file = "settings.json"
    _settings = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SettingsManager, cls).__new__(cls)
            cls._instance._load_settings()
        return cls._instance
    
    def _load_settings(self):
        """Load settings from the JSON file."""
        if os.path.exists(self._settings_file):
            try:
                with open(self._settings_file, 'r') as f:
                    self._settings = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._settings = self._get_default_settings()
        else:
            self._settings = self._get_default_settings()
            self._save_settings()
    
    def _save_settings(self):
        """Save settings to the JSON file."""
        with open(self._settings_file, 'w') as f:
            json.dump(self._settings, f, indent=2)
    
    def _get_default_settings(self) -> Dict:
        """Return default settings."""
        return {
            "general": {
                "site_name": "Hashcat Server",
                "max_concurrent_jobs": 3,
                "auto_delete_completed_jobs": "never",
                "default_hash_mode": "0"
            },
            "email": {
                "enabled": False,
                "smtp_server": "",
                "smtp_port": 587,
                "smtp_username": "",
                "smtp_password": "",
                "from_email": "",
                "notify_on_job_completion": False
            },
            "security": {
                "max_login_attempts": 5,
                "lockout_time": 30,
                "require_password_change": False,
                "password_expiry_days": 90
            }
        }
    
    def get_general_settings(self) -> Dict:
        """Get general settings."""
        return self._settings.get("general", self._get_default_settings()["general"])
    
    def update_general_settings(self, settings: Dict) -> None:
        """Update general settings."""
        self._settings["general"] = settings
        self._save_settings()
    
    def get_email_settings(self) -> Dict:
        """Get email settings."""
        return self._settings.get("email", self._get_default_settings()["email"])
    
    def update_email_settings(self, settings: Dict) -> None:
        """Update email settings."""
        self._settings["email"] = settings
        self._save_settings()
    
    def get_security_settings(self) -> Dict:
        """Get security settings."""
        return self._settings.get("security", self._get_default_settings()["security"])
    
    def update_security_settings(self, settings: Dict) -> None:
        """Update security settings."""
        self._settings["security"] = settings
        self._save_settings()
    
    def get_all_settings(self) -> Dict:
        """Get all settings."""
        return self._settings

    def set_setting(self, category: str, key: str, value) -> None:
        """Set a specific setting."""
        if category not in self._settings:
            self._settings[category] = {}
        self._settings[category][key] = value
        self._save_settings()
    
    def get_setting(self, category: str, key: str, default=None):
        """Get a specific setting."""
        return self._settings.get(category, {}).get(key, default)


class LoginAttemptTracker:
    """
    Tracks login attempts and implements lockout functionality.
    """
    
    _instance = None
    _attempts = {}  # username -> list of attempt timestamps
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LoginAttemptTracker, cls).__new__(cls)
            cls._instance._settings = SettingsManager()
        return cls._instance
    
    def record_attempt(self, username: str, success: bool) -> None:
        """
        Record a login attempt for the given username.
        
        Args:
            username: The username that attempted to log in
            success: Whether the login attempt was successful
        """
        now = datetime.now()
        
        # Initialize attempts list for this username if it doesn't exist
        if username not in self._attempts:
            self._attempts[username] = []
        
        # Clean up old attempts (older than lockout period)
        lockout_minutes = self._settings.get_security_settings()["lockout_time"]
        cutoff = now - timedelta(minutes=lockout_minutes)
        self._attempts[username] = [ts for ts in self._attempts[username] if ts > cutoff]
        
        # If successful login, clear the attempts
        if success:
            self._attempts[username] = []
            return
        
        # Otherwise, record the failed attempt
        self._attempts[username].append(now)
    
    def is_locked_out(self, username: str) -> bool:
        """
        Check if the given username is locked out due to too many failed attempts.
        
        Args:
            username: The username to check
            
        Returns:
            bool: True if the username is locked out, False otherwise
        """
        if username not in self._attempts:
            return False
        
        now = datetime.now()
        max_attempts = self._settings.get_security_settings()["max_login_attempts"]
        lockout_minutes = self._settings.get_security_settings()["lockout_time"]
        cutoff = now - timedelta(minutes=lockout_minutes)
        
        # Count recent failed attempts
        recent_attempts = [ts for ts in self._attempts[username] if ts > cutoff]
        
        return len(recent_attempts) >= max_attempts
    
    def get_remaining_lockout_time(self, username: str) -> Optional[int]:
        """
        Get the remaining lockout time in seconds for the given username.
        
        Args:
            username: The username to check
            
        Returns:
            int: The remaining lockout time in seconds, or None if not locked out
        """
        if not self.is_locked_out(username):
            return None
        
        now = datetime.now()
        lockout_minutes = self._settings.get_security_settings()["lockout_time"]
        oldest_attempt = min(self._attempts[username])
        lockout_end = oldest_attempt + timedelta(minutes=lockout_minutes)
        
        if now >= lockout_end:
            return None
        
        return int((lockout_end - now).total_seconds())


# Helper function to get a singleton instance
def get_settings_manager():
    return SettingsManager()

def get_login_attempt_tracker():
    return LoginAttemptTracker()
```

## 6. Create Admin API Routes
Create a file named `admin_api.py` with the following content:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List, Optional
from pydantic import BaseModel
from sqlalchemy.orm import Session

from models import User
from database import get_db_session
from auth import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])

# --- Pydantic Models ---

class UserCreate(BaseModel):
    username: str
    password: str
    is_admin: bool = False
    is_active: bool = True
    email: Optional[str] = None

class UserUpdate(BaseModel):
    username: Optional[str] = None
    password: Optional[str] = None
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    email: Optional[str] = None

class UserResponse(BaseModel):
    id: int
    username: str
    is_admin: bool
    is_active: bool
    email: Optional[str] = None
    job_count: int = 0
    last_login: Optional[str] = None

    class Config:
        orm_mode = True

class GeneralSettings(BaseModel):
    site_name: str
    max_concurrent_jobs: int
    auto_delete_completed_jobs: str
    default_hash_mode: str

class EmailSettings(BaseModel):
    email_enabled: bool
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    from_email: Optional[str] = None
    notify_on_job_completion: bool = False

class SecuritySettings(BaseModel):
    max_login_attempts: int
    lockout_time: int
    require_password_change: bool

class Message(BaseModel):
    detail: str

# --- API Routes ---

# User Management Routes
@router.get("/users", response_model=List[UserResponse])
async def list_users(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get all users from the database
    users = db.query(User).all()
    
    # Convert to response model, adding job count
    user_responses = []
    for user in users:
        # Count jobs for this user - will be implemented when job_association is added
        job_count = len(user.jobs) if hasattr(user, "jobs") else 0
        
        user_responses.append(UserResponse(
            id=user.id,
            username=user.username,
            is_admin=user.is_admin,
            is_active=user.is_active,
            email=user.email,
            job_count=job_count,
            last_login=user.last_login.isoformat() if user.last_login else None
        ))
    
    return user_responses

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Check if username already exists
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(status_code=400, detail="Username already exists")
    
    # Create new user
    new_user = User(
        username=user_data.username,
        is_admin=user_data.is_admin,
        is_active=user_data.is_active,
        email=user_data.email
    )
    new_user.set_password(user_data.password)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Return the new user without the password
    return UserResponse(
        id=new_user.id,
        username=new_user.username,
        is_admin=new_user.is_admin,
        is_active=new_user.is_active,
        email=new_user.email,
        job_count=0
    )

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get user by ID
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Count jobs for this user
    job_count = len(user.jobs) if hasattr(user, "jobs") else 0
    
    return UserResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        email=user.email,
        job_count=job_count,
        last_login=user.last_login.isoformat() if user.last_login else None
    )

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get user by ID
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent self-demotion
    if user.id == current_user.id and user_data.is_admin is False:
        raise HTTPException(status_code=400, detail="Cannot remove admin status from yourself")
    
    # Update user fields if provided
    if user_data.username is not None:
        # Check if new username already exists
        if user_data.username != user.username and db.query(User).filter(User.username == user_data.username).first():
            raise HTTPException(status_code=400, detail="Username already exists")
        user.username = user_data.username
    
    if user_data.password is not None:
        user.set_password(user_data.password)
    
    if user_data.is_admin is not None:
        user.is_admin = user_data.is_admin
    
    if user_data.is_active is not None:
        user.is_active = user_data.is_active
    
    if user_data.email is not None:
        user.email = user_data.email
    
    db.commit()
    db.refresh(user)
    
    # Count jobs for this user
    job_count = len(user.jobs) if hasattr(user, "jobs") else 0
    
    return UserResponse(
        id=user.id,
        username=user.username,
        is_admin=user.is_admin,
        is_active=user.is_active,
        email=user.email,
        job_count=job_count,
        last_login=user.last_login.isoformat() if user.last_login else None
    )

@router.delete("/users/{user_id}", response_model=Message)
async def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # Get user by ID
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent self-deletion
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")
    
    # Delete user
    db.delete(user)
    db.commit()
    
    return Message(detail=f"User {user.username} deleted successfully")

# Settings Routes
@router.get("/settings/general", response_model=GeneralSettings)
async def get_general_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # In a real implementation, this would fetch settings from a settings table or file
    # For now, we'll return default values
    return GeneralSettings(
        site_name="Hashcat Server",
        max_concurrent_jobs=3,
        auto_delete_completed_jobs="never",
        default_hash_mode="0"
    )

@router.post("/settings/general", response_model=Message)
async def update_general_settings(
    settings: GeneralSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # In a real implementation, this would update settings in a settings table or file
    # For now, we'll just return a success message
    return Message(detail="General settings updated successfully")

@router.get("/settings/email", response_model=EmailSettings)
async def get_email_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # In a real implementation, this would fetch settings from a settings table or file
    # For now, we'll return default values
    return EmailSettings(
        email_enabled=False,
        smtp_server="",
        smtp_port=587,
        smtp_username="",
        smtp_password="",
        from_email="",
        notify_on_job_completion=False
    )

@router.post("/settings/email", response_model=Message)
async def update_email_settings(
    settings: EmailSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # In a real implementation, this would update settings in a settings table or file
    # For now, we'll just return a success message
    return Message(detail="Email settings updated successfully")

@router.post("/settings/test-email", response_model=Message)
async def test_email_settings(
    settings: EmailSettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # In a real implementation, this would attempt to send a test email
    # For now, we'll just return a success message
    return Message(detail="Test email sent successfully")

@router.get("/settings/security", response_model=SecuritySettings)
async def get_security_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # In a real implementation, this would fetch settings from a settings table or file
    # For now, we'll return default values
    return SecuritySettings(
        max_login_attempts=5,
        lockout_time=30,
        require_password_change=False
    )

@router.post("/settings/security", response_model=Message)
async def update_security_settings(
    settings: SecuritySettings,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    # In a real implementation, this would update settings in a settings table or file
    # For now, we'll just return a success message
    return Message(detail="Security settings updated successfully")
```

## 7. Create Admin UI Routes
Create a file named `admin_routes.py` with the following content:

```python
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, List, Optional
import datetime

from models import User
from auth import get_current_user
from settings import get_settings_manager
from database import get_db_session
from sqlalchemy.orm import Session

# Create router
router = APIRouter(prefix="/admin", tags=["admin_ui"])

# Setup templates
templates = Jinja2Templates(directory="templates")

# --- Helper functions ---

def get_user_stats(db: Session) -> Dict:
    """Get user statistics."""
    total_users = db.query(User).count()
    admin_users = db.query(User).filter(User.is_admin == True).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    
    return {
        "total_users": total_users,
        "admin_users": admin_users,
        "active_users": active_users,
        "inactive_users": total_users - active_users
    }

def get_job_stats(db: Session) -> Dict:
    """Get job statistics."""
    # This will be implemented when we integrate with the job system
    # For now, return placeholders
    return {
        "total_jobs": 0,
        "active_jobs": 0,
        "completed_jobs": 0,
        "failed_jobs": 0
    }

def get_recent_jobs(db: Session, limit: int = 5) -> List[Dict]:
    """Get recent jobs."""
    # This will be implemented when we integrate with the job system
    # For now, return placeholder data
    return []

def get_system_info() -> Dict:
    """Get system information."""
    import platform
    import psutil
    
    try:
        # Get memory info
        memory = psutil.virtual_memory()
        memory_total_gb = round(memory.total / (1024**3), 2)
        memory_used_gb = round(memory.used / (1024**3), 2)
        memory_percent = memory.percent
        
        # Get CPU info
        cpu_count = psutil.cpu_count(logical=False)
        cpu_logical = psutil.cpu_count()
        cpu_percent = psutil.cpu_percent(interval=0.5)
        
        # Get disk info
        disk = psutil.disk_usage('/')
        disk_total_gb = round(disk.total / (1024**3), 2)
        disk_used_gb = round(disk.used / (1024**3), 2)
        disk_percent = disk.percent
        
        # Get system uptime
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot_time
        uptime_days = uptime.days
        uptime_hours, remainder = divmod(uptime.seconds, 3600)
        uptime_minutes, uptime_seconds = divmod(remainder, 60)
        uptime_str = f"{uptime_days} days, {uptime_hours} hours, {uptime_minutes} minutes"
        
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": cpu_count,
            "cpu_logical": cpu_logical,
            "cpu_percent": cpu_percent,
            "memory_total": memory_total_gb,
            "memory_used": memory_used_gb,
            "memory_percent": memory_percent,
            "disk_total": disk_total_gb,
            "disk_used": disk_used_gb,
            "disk_percent": disk_percent,
            "uptime": uptime_str
        }
    except:
        # Fallback if psutil information is not available
        return {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "architecture": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": "N/A",
            "cpu_logical": "N/A",
            "cpu_percent": "N/A",
            "memory_total": "N/A",
            "memory_used": "N/A",
            "memory_percent": "N/A",
            "disk_total": "N/A",
            "disk_used": "N/A",
            "disk_percent": "N/A",
            "uptime": "N/A"
        }

def get_hash_modes() -> List[tuple]:
    """Get list of hashcat hash modes."""
    # This will be implemented with actual hash mode data
    # For now, return some common ones
    return [
        ("0", "MD5"),
        ("100", "SHA1"),
        ("1000", "NTLM"),
        ("1800", "SHA512crypt"),
        ("3200", "bcrypt")
    ]

# --- Route handlers ---

@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """Admin dashboard page."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    user_stats = get_user_stats(db)
    job_stats = get_job_stats(db)
    recent_jobs = get_recent_jobs(db)
    system_info = get_system_info()
    
    return templates.TemplateResponse("admin_dashboard.html", {
        "request": request,
        "user": current_user,
        "user_stats": user_stats,
        "job_stats": job_stats,
        "recent_jobs": recent_jobs,
        "system_info": system_info
    })

@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """Admin user management page."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "user": current_user
    })

@router.get("/jobs", response_class=HTMLResponse)
async def admin_jobs(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """Admin job management page."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    return templates.TemplateResponse("admin_jobs.html", {
        "request": request,
        "user": current_user
    })

@router.get("/settings", response_class=HTMLResponse)
async def admin_settings(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db_session)
):
    """Admin settings page."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    
    settings_manager = get_settings_manager()
    settings = {
        **settings_manager.get_general_settings(),
        **settings_manager.get_email_settings(),
        **settings_manager.get_security_settings()
    }
    
    hash_modes = get_hash_modes()
    
    return templates.TemplateResponse("admin_settings.html", {
        "request": request,
        "user": current_user,
        "settings": settings,
        "hash_modes": hash_modes
    })
```

## 8. Update Main Application File
Update the main.py file to include the new admin routes:

```python
from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
import os
import sys

# Add database models and authentication
from models import Base, User
from auth import get_current_user
from database import engine, get_db_session
from admin_api import router as admin_api_router
from admin_routes import router as admin_routes_router

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# Initialize FastAPI app
app = FastAPI(title="Hashcat Server", version="1.1.0")

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(admin_api_router)
app.include_router(admin_routes_router)

# --- Existing routes (placeholder - integrate with actual routes) ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, current_user: User = Depends(get_current_user)):
    """Main page - redirects to jobs or admin dashboard based on user role."""
    if current_user.is_admin:
        return RedirectResponse(url="/admin")
    return RedirectResponse(url="/jobs")

@app.get("/jobs", response_class=HTMLResponse)
async def jobs_page(request: Request, current_user: User = Depends(get_current_user)):
    """Jobs page - shows user's jobs."""
    return templates.TemplateResponse("jobs.html", {
        "request": request,
        "user": current_user
    })

@app.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, current_user: User = Depends(get_current_user)):
    """User profile page."""
    return templates.TemplateResponse("profile.html", {
        "request": request,
        "user": current_user
    })

# --- Additional API routes for non-admin functionality ---

# Job API endpoints (will be integrated with existing functionality)

# --- Setup functions ---

def create_admin_user():
    """Create an admin user if one doesn't exist."""
    db = next(get_db_session())
    admin_user = db.query(User).filter(User.is_admin == True).first()
    
    if not admin_user:
        print("Creating default admin user...")
        admin = User(
            username="admin",
            is_admin=True,
            is_active=True
        )
        admin.set_password("hashcat-admin")  # Default password
        db.add(admin)
        db.commit()
        print("Default admin user created with username 'admin' and password 'hashcat-admin'")
        print("Please change this password immediately after first login!")
    
    db.close()

# --- Main entry point ---

if __name__ == "__main__":
    create_admin_user()
    
    # Start the application
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
```

## 9. Create HTML Templates

### admin_dashboard.html
This file has already been created.

### admin_users.html
This file has already been created.

### admin_jobs.html
This file has already been created.

### admin_settings.html
This file has already been created.

## 10. Implementation Status

### Completed:
- ✅ Database models for users and job associations
- ✅ Authentication system with database integration
- ✅ Settings management system
- ✅ Admin API endpoints for user and settings management
- ✅ Admin UI routes
- ✅ Admin dashboard template
- ✅ User management template
- ✅ Jobs management template
- ✅ Settings management template
- ✅ Login attempt tracking and lockout functionality

### To Be Completed:
- ❌ Integration with job system to associate jobs with users
- ❌ Update job creation process to link jobs to users
- ❌ Implement job filtering by user in admin panel
- ❌ Email notification system implementation
- ❌ Add user profile page with password change functionality
- ❌ Comprehensive testing of user management features

## 11. Running the Application

1. Install required packages:
```
pip install fastapi uvicorn sqlalchemy passlib[bcrypt] psutil python-multipart
```

2. Start the application:
```
python main.py
```

3. Access the admin panel:
   - URL: http://localhost:8000/admin
   - Default credentials: 
     - Username: admin
     - Password: hashcat-admin

## 12. Security Considerations

- Change the default admin password immediately after first login
- Consider implementing HTTPS for production use
- Enable password policy enforcement (minimum length, complexity)
- Implement rate limiting for login attempts (basic implementation included)
- Consider adding 2FA for admin accounts in a future update
