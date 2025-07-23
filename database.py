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
