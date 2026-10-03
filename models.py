from sqlalchemy import Column, Integer, String, ForeignKey,JSON
from database import Base

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    role = Column(String, nullable=False)  # 'teacher' ya 'student'

class Student(Base):
    __tablename__ = "students"
    id = Column(Integer, primary_key=True, index=True)
    user_id=Column(Integer, ForeignKey("users.id"),unique=True, nullable=False)
    student_name = Column(String, nullable=False)
    email = Column(String,unique=True, index=True)
    contact = Column(String, nullable=False, unique=True, index=True)
    batch_id = Column(String,nullable=False)

class Teacher(Base):
    __tablename__ = "teachers"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    teacher_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True)
    contact = Column(String, nullable=False, unique=True, index=True)                
    department = Column(String, nullable=False)
   
class Quiz(Base):
    __tablename__ = "quizzes"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    teacher_id = Column(Integer, ForeignKey("teachers.id"))
    batch_id = Column(String, index=True)

class Question(Base):
    __tablename__ = "questions"
    id = Column(Integer, primary_key=True, index=True)
    quiz_id = Column(Integer, ForeignKey("quizzes.id"))
    question_text = Column(String)
    options = Column(JSON) # Ab ye direct Python lists/dicts handle karega!
    correct_answer = Column(String)

class Attempt(Base):
    __tablename__ = "attempts"
    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"))
    quiz_id = Column(Integer, ForeignKey("quizzes.id"))
    score = Column(Integer, nullable=False)

"""
primary_key=True: Uniquely identifies each row. It automatically prevents duplicates and nulls for that specific column, acting as the absolute reference point for the record.
index=True: Builds a B-Tree data structure under the hood. It optimizes read performance, dropping lookup time complexity from $O(N)$ (full table scan) to $O(\log N)$ for frequently queried columns like email or batch_id.
unique=True: Enforces strict data integrity. It tells the database to reject the insert and throw an IntegrityError if someone tries to save a value that already exists in that column (critical for email, contact, and 1-to-1 user_id links).
nullable=False: The database-level "required field". It prevents the application from saving empty (NULL) values, ensuring you don't end up with incomplete domain profiles.
ForeignKey("table.column"): The relational glue. It enforces referential integrity, ensuring a record in one table perfectly maps to a valid record in another (e.g., ensuring an Attempt belongs to a real Student and a real Quiz).
"""