from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# to load SQLALCHEMY_DATABASE_URL from.env
import os
from dotenv import load_dotenv
load_dotenv()

# SQLite DB file ka naam
DATABASE_URL =os.getenv("DATABASE_URL")

# mysql coonection
engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()