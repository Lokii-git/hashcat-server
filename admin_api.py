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
