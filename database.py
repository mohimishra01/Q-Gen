from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# to load SQLALCHEMY_DATABASE_URL from.env
import os
from dotenv import load_dotenv
load_dotenv()

# SQLite DB file ka naam
DATABASE_URL =os.getenv("DATABASE_URL")

# SQLite me 'check_same_thread=False' zaroori hota hai FastAPI (multi-thread) ke liye
engine = create_engine(
    DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()