import os
from datetime import datetime
from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker
from passlib.context import CryptContext

Base = declarative_base()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# User model
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    email = Column(String, nullable=True)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)
    
    # Relationship to jobs
    jobs = relationship("JobAssociation", back_populates="user")
    
    def verify_password(self, password):
        return pwd_context.verify(password, self.password_hash)
    
    @staticmethod
    def get_password_hash(password):
        return pwd_context.hash(password)

# Job association model to link users with jobs
class JobAssociation(Base):
    __tablename__ = "job_associations"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    job_id = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship to user
    user = relationship("User", back_populates="jobs")

# Database setup
def get_db_engine():
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hashcat_server.db")
    return create_engine(f"sqlite:///{db_path}")

def get_db_session():
    engine = get_db_engine()
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return SessionLocal()

def init_db():
    engine = get_db_engine()
    Base.metadata.create_all(bind=engine)
    
    # Create admin user if it doesn't exist
    session = get_db_session()
    admin = session.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            password_hash=User.get_password_hash("password"),
            email="admin@example.com",
            is_admin=True
        )
        session.add(admin)
        session.commit()
        print("Created default admin user: admin / password")
    session.close()
