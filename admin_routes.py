from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, List, Optional

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
