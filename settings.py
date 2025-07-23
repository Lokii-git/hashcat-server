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
