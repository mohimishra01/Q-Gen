#for auth and rbac
from fastapi import FastAPI,Depends,HTTPException
from fastapi import Form, File, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel
from typing import Optional,List

#for jwt creation and password hashing
from jose import jwt
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext

#for database integration
from sqlalchemy.orm import Session
from sqlalchemy import desc

# to load used signing algo(signature) & secret_key for jwt token creation from.env
import os
from dotenv import load_dotenv
load_dotenv()

#user_created_files import
import ai_engine
import dtos
import models
from database import engine, SessionLocal


# Yahan par magic hota hai! Ye line models.py ki saari tables DB me create kar degi.
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- JWT & Auth Config ---
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_schema = OAuth2PasswordBearer(tokenUrl="login")


# Dependency: API endpoints ko DB connection dene ke liye
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# --- APIs ---

# 1. REGISTER API (Naya user banayega)
@app.post("/register") #fastapi path operation decorater
def register(user: dtos.NewUser, db: Session = Depends(get_db)):
    # Check agar user pehle se hai
    existing_user = db.query(models.User).filter(models.User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Password hash karo aur DB me save karo
    hashed_pwd = hash_password(user.password)
    new_user = models.User(username=user.username, hashed_password=hashed_pwd, role=user.role)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    return {"message": "User created successfully", "username": new_user.username, "role": new_user.role}

# 2. LOGIN API (Real DB se check karega)
@app.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    # Fake DB ki jagah ab real DB me user dhoondho
    user = db.query(models.User).filter(models.User.username == form_data.username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    # Token me username ke sath 'role' bhi daal do RBAC ke liye!
    token = create_token({"sub": user.username,"role": user.role, "user_id": user.id})

    return {"access_token": token, "token_type": "bearer",}

# 3. VERIFY TOKEN (authentication)
def verification(token: str = Depends(oauth2_schema)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload  # Ab sirf username nahi, pura payload bhejenge (jisme role bhi hai)
    except:
        raise HTTPException(status_code=401, detail="Unauthorized access")


# ==========================================
# STUDENT APIs
# ==========================================

# 1.1 student profile data saving in db
@app.post("/student/complete_profile")
def complete_profile(profile: dtos.StudentProfileCreate, current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    # 1. Only students can access this
    if current_user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Only students can complete a student profile")

    user_id=current_user.get("user_id")
    existing_student = db.query(models.Student).filter(models.Student.user_id == user_id).first()
    if existing_student:
        raise HTTPException(status_code=400, detail="Profile already exists!")

    # 2. Create the domain record linking to the auth user_id
    new_student = models.Student(
        user_id=user_id,
        student_name=profile.student_name,
        email=profile.email,
        contact=profile.contact,
        batch_id=profile.batch_id
    )
    
    db.add(new_student)
    db.commit()
    
    return {"message": "Profile completed successfully!"}

#1.2 checking the profile complete before accessing other services
@app.get("/student/check_profile")
def check_profile(current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    #RBAC
    if current_user.get("role") != "student":
           raise HTTPException(status_code=403, detail="Only students can complete a student profile")
   
    # Check if a student record exists for this user_id
    student = db.query(models.Student).filter(models.Student.user_id == current_user.get("user_id")).first()
    return {"profile_completed": student is not None}

#1.3 provide the profile data to student on request
@app.get("/student/me")
def get_student_profile(current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    # 1. Fetch the domain profile using the Auth ID
    student = db.query(models.Student).filter(models.Student.user_id == current_user.get("user_id")).first()
    
    if not student:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    # 2. Return the student-specific data
    return {
        "name": student.student_name, # Note your DB column is student_name
        "email": student.email,
        "contact": student.contact,
        "batch_id": student.batch_id  # Student specific field
    }


# 2 AVAILABLE QUIZZES (Batch based filtering)
@app.get("/available-quizzes")
def get_available_quizzes(current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    if current_user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Access denied")

    # 1. extracting the Student ki ID & batch
    student = db.query(models.Student).filter(models.Student.user_id == current_user.get("user_id")).first()

    if not student:
        return [] # Returns an empty list 
    
    student_batch = student.batch_id

    # 2. Subquery: Wo saari Quiz IDs lao jo student already attempt kar chuka hai
    attempted_quiz_ids = db.query(models.Attempt.quiz_id).filter(models.Attempt.student_id == student.id)

    
    # 3. Main Query: Batch match karo AUR (~in_) filter lagao ki ID attempted list me NA ho
    available_quizzes = db.query(models.Quiz).filter(
             models.Quiz.batch_id == student_batch,
             ~models.Quiz.id.in_(attempted_quiz_ids)  # '~' ka matlab SQL me NOT hota hai
        ).all()
    
    return available_quizzes

# 3. GET QUIZ BY ID (For attempting the quiz - Hides correct answers)
@app.get("/quiz/{quiz_id}", response_model=dtos.QuizSentDB)
def get_quiz_to_attempt(quiz_id: int, current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    if current_user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Access denied")
    
    quiz = db.query(models.Quiz).filter(models.Quiz.id == quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")
        
    questions = db.query(models.Question).filter(models.Question.quiz_id == quiz_id).all()
    
    #  Pydantic khud 'correct_answer' hata dega.
    return {"quiz_title": quiz.title, "questions": questions}

# 4. SUBMIT QUIZ & EVALUATION ENGINE
@app.post("/submit-quiz")
def submit_quiz(submission: dtos.QuizSubmit, current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    # Check if user is a student
    if current_user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Only students can submit quizzes")
        
    student = db.query(models.Student).filter(models.Student.user_id== current_user.get("user_id")).first()

    if not student:
        raise HTTPException(status_code=403, detail="Student profile incomplete. Please update your profile first.")

    # Check if student already submitted this quiz
    #"Double Submit" ya "Race Condition" kehte hain,network slow hone ki wajah se request retry ho jate hai
    existing_attempt = db.query(models.Attempt).filter_by(
        student_id=student.id, 
        quiz_id=submission.quiz_id
    ).first()
    
    if existing_attempt:
        raise HTTPException(status_code=400, detail="You have already attempted this quiz!")

    #  Database se saare questions ek baar me fetch kar lo
    db_questions = db.query(models.Question).filter(models.Question.quiz_id == submission.quiz_id).all()
    
    # Simple loop se score calculate karo
    score = 0
    for student_ans in submission.answers:
        for real_q in db_questions:
            # Agar Question ID match kare AUR answer bhi match kare
            if student_ans.question_id == real_q.id and student_ans.selected_option == real_q.correct_answer:
                score += 1
                break  # Match mil gaya, agle answer par jao
                
    # Score DB me save karo
    attempt = models.Attempt(student_id=student.id, quiz_id=submission.quiz_id, score=score)
    db.add(attempt)
    db.commit()
    
    return {"message": "Quiz submitted Successfully!", "total_Questions": len(db_questions),"score": score}

# 5. MY SCORES API (Student)
@app.get("/my-scores", response_model=List[dtos.ScoreResponse])
def get_my_scores(current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    # 1. RBAC Check
    if current_user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Access denied")
        
    student = db.query(models.Student).filter(models.Student.user_id == current_user.get("user_id")).first()

    if not student:
        return []
    
    # 2. SQL Join: Attempts aur Quiz table ko jodna
    scores_data = db.query(
        models.Attempt.quiz_id,
        models.Quiz.title.label("quiz_title"),
        models.Attempt.score
    ).join(models.Quiz, models.Attempt.quiz_id == models.Quiz.id)\
     .filter(models.Attempt.student_id == student.id).all()
    
    # FastAPI aur Pydantic automatically is data ko List[ScoreResponse] me format kar denge
    return scores_data

# ==========================================
# TEACHER APIs
# ==========================================

# 1.1 teacher profile data saving in db
@app.post("/teacher/complete_profile")
def complete_profile(profile: dtos.TeacherProfileCreate, current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    # 1. Only students can access this
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Only teachers can complete a teacher profile")

    user_id=current_user.get("user_id")
    existing_teacher = db.query(models.Teacher).filter(models.Teacher.user_id == user_id).first()
    if existing_teacher:
        raise HTTPException(status_code=400, detail="Profile already exists!")

    # 2. Create the domain record linking to the auth user_id
    new_teacher = models.Teacher(
        user_id=user_id,
        teacher_name=profile.teacher_name,
        email=profile.email,
        contact=profile.contact,
        department=profile.department
    )
    
    db.add(new_teacher)
    db.commit()
    
    return {"message": "Profile completed successfully!"}

#1.2 checking the completion of teacher profile before providing other services
@app.get("/teacher/check_profile")
def check_profile(current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    #RBAC
    if current_user.get("role") != "teacher":
           raise HTTPException(status_code=403, detail="Only teachers are allowed")
   
    # Check if a student record exists for this user_id
    teacher = db.query(models.Teacher).filter(models.Teacher.user_id == current_user.get("user_id")).first()
    return {"profile_completed": teacher is not None}

#1.3 to provide profile data to teacher on request
@app.get("/teacher/me")
def get_teacher_profile(current_user: dict = Depends(verification), db: Session = Depends(get_db)):

    #1  RBAC (Gatekeeper): Sirf teachers ko allow karo
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Access denied: Only teachers can create quizzes")
        
    # 1. Fetch the domain profile using the Auth ID
    teacher = db.query(models.Teacher).filter(models.Teacher.user_id == current_user.get("user_id")).first()
    
    if not teacher:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    # 2. Return the data (FastAPI automatically converts this to JSON)
    return {
        "name": teacher.teacher_name,
        "email": teacher.email,
        "contact": teacher.contact,
        "department": teacher.department
    }


# @app.post("/create-quiz") ---> generate_preview ---> /save_quiz (to allow teacher to see the quiz if he assured with it can save in db)

#2.1 (generation of quiz through llm asynchronously)
@app.post("/generate_preview")
async def generate_quiz(
    batch_id: str = Form(...),
    topic: str = Form(...),
    num_questions: int = Form(...),
    generation_mode: str = Form(...),
    start_page: Optional[int] = Form(None), # Optional kyunki sirf method 2 me aayega
    end_page: Optional[int] = Form(None),   # Optional kyunki sirf method 2 me aayega
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(verification)
):  
    #1  RBAC (Gatekeeper): Sirf teachers ko allow karo
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Access denied: Only teachers can create quizzes")
    
    # 2. Extract File Bytes (If uploaded)
    file_bytes = None
    if file:
        file_bytes = await file.file.read() # File ko memory me read kar liya and this is non-blocking
   
    # 3. LANGCHAIN AI PIPELINE (llm question generation)
    
    # llm is instructed through dto to generate ouput in list of question(also specified in dto)
    generated_questions = []

    generated_questions =  await ai_engine.generate_quiz_via_llm(mode=generation_mode,
                                    topic=topic,
                                    count=num_questions,
                                    file_bytes=file_bytes,
                                    start_page=start_page,
                                    end_page=end_page
                                    )
    if generated_questions:
        return {"message":"preview generated, have a look","questions":generated_questions}
    else:
        raise HTTPException(status_code=500,detail="Failed to generate quiz: mentioned topic is not present in pdf")

#2.2 (saving the quiz after teacher confirmation)
@app.post("/save_quiz")
def save_quiz(quiz_to_save:dtos.QuizSaveSchema, current_user: dict = Depends(verification), db: Session = Depends(get_db)):
        #  RBAC: Sirf teachers ko allow karo
        if current_user.get("role") != "teacher":
            raise HTTPException(status_code=403, detail="Access denied: Only teachers can create quizzes")
        
        #  Token se username nikal kar uski user_ID fetch karenge
        teacher = db.query(models.User).filter(models.User.username == current_user.get("sub")).first()
        
        new_quiz = models.Quiz(
            title=f"{quiz_to_save.topic} Quiz",
            batch_id=quiz_to_save.batch_id, 
            teacher_id=teacher.id
            )
        db.add(new_quiz)
        db.commit()
        db.refresh(new_quiz) # it makes a select query to fetch the db auto generated  new_quiz.id and bind it the the python object

        #  Loop chala kar saare questions ko DB me add krdenge
        for q in quiz_to_save.questions:
            curr_question = models.Question(
            quiz_id=new_quiz.id,
            question_text=q.question_text,
            options=q.options, 
            correct_answer=q.correct_answer
            )
            db.add(curr_question)
    
        # Saare questions ek hi baar me commit karo (Performance optimization)
        db.commit() 
        return {"message": "Quiz created successfully!", "quiz_id": new_quiz.id}

#3
@app.get("/my-quizzes",response_model=List[dtos.teacher_created_quizes])
def get_my_quizzes(current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    # 1. RBAC Check
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 2. Current teacher ko DB me dhoondho
    teacher = db.query(models.User).filter(models.User.username == current_user.get("sub")).first()
    
    # 3. Sirf wahi quiz return karo jinka teacher_id match karta hai
    quizzes = db.query(models.Quiz).filter(models.Quiz.teacher_id == teacher.id).all()
    
    return quizzes

# 4. LEADERBOARD API (Teacher API)
@app.get("/quiz/{quiz_id}/leaderboard")
def get_leaderboard(quiz_id: int, current_user: dict = Depends(verification), db: Session = Depends(get_db)):
    # 1. RBAC: Sirf teacher hi leaderboard dekh sakta hai
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Access denied")
    
    # 2. SQL Join & Sort: Attempts aur Users table ko jodna aur highest score upar rakhna
    leaderboard_data = db.query(
        models.Student.student_name, 
        models.Attempt.score
    ).join(models.Attempt, models.Student.id == models.Attempt.student_id)\
     .filter(models.Attempt.quiz_id == quiz_id)\
     .order_by(desc(models.Attempt.score)).all()
    
    # 3. Data Formatting: Frontend ke liye clean JSON (List of dictionaries) 
    result = [{"username": row.student_name, "score": row.score} for row in leaderboard_data]
    
    return {"quiz_id": quiz_id, "leaderboard": result}
