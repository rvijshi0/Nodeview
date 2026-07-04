import datetime
import os
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Auto-detect database: Docker (PostgreSQL) vs Local development (SQLite)
DATABASE_URL = os.environ.get("DATABASE_URL", None)

if not DATABASE_URL:
    # Local development — use SQLite (no server required)
    _db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nodeview.db")
    DATABASE_URL = f"sqlite:///{_db_path}"
    print(f"[DB] Using local SQLite database: {_db_path}")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)

class NetworkRange(Base):
    __tablename__ = "networks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    cidr_range = Column(String, unique=True, nullable=False)  # e.g., 192.168.1.0/24
    scan_frequency_seconds = Column(Integer, default=60)

class Agent(Base):
    __tablename__ = "agents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    ip_address = Column(String, nullable=True)
    mac_address = Column(String, nullable=True)
    status = Column(String, default="offline")  # online, offline
    api_key = Column(String, unique=True, index=True, nullable=False)
    last_seen = Column(DateTime, default=datetime.datetime.utcnow)

class DiagnosticTest(Base):
    """Tracks diagnostic test history for audit and troubleshooting review."""
    __tablename__ = "diagnostic_tests"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(String, unique=True, index=True, nullable=False)
    source_agent_name = Column(String, nullable=False)
    target_ip = Column(String, nullable=False)
    target_port = Column(Integer, nullable=False)
    protocol = Column(String, default="tcp")
    spoof_ip = Column(String, nullable=True)
    spoof_mac = Column(String, nullable=True)
    test_type = Column(String, default="tcp_test")  # tcp_test, spoof_test, traceroute, listen
    status = Column(String, default="initiated")  # initiated, in_progress, success, failed, timeout
    result_details = Column(Text, nullable=True)
    is_collaborative = Column(Boolean, default=False)
    target_agent_name = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

class InternetTarget(Base):
    __tablename__ = "internet_targets"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String, unique=True, nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

class AgentTraceroute(Base):
    __tablename__ = "agent_traceroutes"

    id = Column(Integer, primary_key=True, index=True)
    agent_name = Column(String, nullable=False)
    target_ip = Column(String, nullable=False)
    hops = Column(Text, nullable=False)  # JSON list of hops e.g. '["10.0.10.1", "10.0.1.1", "8.8.8.8"]'
    last_updated = Column(DateTime, default=datetime.datetime.utcnow)

class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)

def init_pg():
    # Attempt creation of all Postgres tables
    try:
        Base.metadata.create_all(bind=engine)
        print("PostgreSQL tables checked/created successfully.")
    except Exception as e:
        print(f"PostgreSQL connection/creation warning: {e}. Ensure DB container is running.")

def get_pg_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
