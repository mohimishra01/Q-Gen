#for auth and rbac
from fastapi import FastAPI,Depends,HTTPException
from fastapi import Form, File, UploadFile
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from typing import Optional,List

#for jwt creation and password hashing
from jose import jwt
from datetime import datetime, timedelta, timezone
from passlib.context import CryptContext

#for database integration
from sqlalchemy.orm import Session
from sqlalchemy import desc
from sqlalchemy.exc import IntegrityError ## duplicate emaail and contact

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


def hash_password(password: str):
    return pwd_context.hash(password)

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def create_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=30)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# ==========================================
# DEPENDENCIES
# ==========================================

# 1.API endpoints ko DB connection dene ke liye
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

#  2.VERIFY TOKEN (authentication)
def verification(token: str = Depends(oauth2_schema)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload  # Ab sirf username nahi, pura payload bhejenge (jisme role bhi hai)
    except:
        raise HTTPException(status_code=401, detail="Unauthorized access")

# 3.ROLE BASED ACCESS: TEACHER
def require_teacher(current_user: dict = Depends(verification)):
    if current_user.get("role") != "teacher":
        raise HTTPException(status_code=403, detail="Access denied: Teachers only")
    return current_user

# 4.ROLE BASED ACCESS: STUDENT 
def require_student(current_user: dict = Depends(verification)):
    if current_user.get("role") != "student":
        raise HTTPException(status_code=403, detail="Access denied: Students only")
    return current_user

# 5.RBAC for generating the quiz preview ("/generate_preview")---
def teacher_batch_ownership(          
    batch_id: int = Form(...),
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    teacher = db.query(models.Teacher).filter(models.Teacher.user_id == current_user.get("user_id")).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    authority= db.query(models.TeacherBatch).filter_by(teacher_id=teacher.id, batch_id=batch_id).first()
    if not authority:
        raise HTTPException(status_code=403, detail="You are not assigned to this batch")
   
    return teacher  # Returns the SQLAlchemy Teacher object directly to endpoints.

# 6.RBAC for saving quiz and access leaderboard( "/save_quiz" & "/quiz/{quiz_id}/leaderboard")---
def teacher_BatchAndQuiz_ownership(          
    quiz_id: Optional[int] = None,
    quiz_to_save: Optional[dtos.QuizSaveSchema] = None,
    current_user: dict = Depends(require_teacher),
    db: Session = Depends(get_db)
):
    teacher = db.query(models.Teacher).filter(models.Teacher.user_id == current_user.get("user_id")).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found")

    # Handles GET /quiz/{quiz_id}/leaderboard
    if quiz_id is not None:
        if not db.query(models.Quiz).filter_by(id=quiz_id, teacher_id=teacher.id).first():
            raise HTTPException(status_code=403, detail="You do not own this quiz")

    # Handles POST /save_quiz
    if quiz_to_save is not None:
        if not db.query(models.TeacherBatch).filter_by(teacher_id=teacher.id, batch_id=quiz_to_save.batch_id).first():
            raise HTTPException(status_code=403, detail="You are not assigned to this batch")

    return teacher

# 7. RBAC: STUDENT (Checks if Quiz belongs to Student's Batch) ---
def check_student_authority(
    quiz_id: Optional[int] = None,                  # Grabs {quiz_id} from URL in GET /quiz/{quiz_id}
    submission: Optional[dtos.QuizSubmit] = None,   # Grabs JSON body in POST /submit-quiz
    current_user: dict = Depends(require_student),  # Chains Role Check + JWT Verification!
    db: Session = Depends(get_db)
):
    student = db.query(models.Student).filter(models.Student.user_id == current_user.get("user_id")).first()
    if not student:
        raise HTTPException(status_code=403, detail="Complete your student profile first")

    target_quiz_id = submission.quiz_id if submission else quiz_id
    quiz = db.query(models.Quiz).filter(models.Quiz.id == target_quiz_id).first()
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    if quiz.batch_id != student.batch_id:
        raise HTTPException(status_code=403, detail="This quiz does not belong to your batch")

    return student  # Returns the SQLAlchemy Student object directly to endpoints

# ==========================================
# SHARED APIs
# ==========================================

# 1. REGISTER API (Naya user banayega)
@app.post("/register") #fastapi path operation decorater
def register(user: dtos.NewUser, db: Session = Depends(get_db)):
    
    # Check agar user pehle se hai
    existing_user = db.query(models.User).filter(models.User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=409, detail="Username already registered")
    
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


# ==========================================
# TEACHER APIs
# ==========================================

# 1.1 teacher profile data saving in db
@app.post("/teacher/complete_profile")
def complete_profile(profile: dtos.TeacherProfileCreate, current_user: dict = Depends(require_teacher), db: Session = Depends(get_db)):
   
    user_id=current_user.get("user_id")
    existing_teacher = db.query(models.Teacher).filter(models.Teacher.user_id == user_id).first()
    if existing_teacher:
        raise HTTPException(status_code=409, detail="Profile already exists!")

    # 2. Create the domain record linking to the auth user_id
    new_teacher = models.Teacher(
        user_id=user_id,
        teacher_name=profile.teacher_name,
        email=profile.email,
        contact=profile.contact,
        department=profile.department
    )
    
    db.add(new_teacher)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That email or contact number is already in use")
    
    return {"message": "Profile completed successfully!"}


#1.2 checking the completion of teacher profile before providing other services
@app.get("/teacher/check_profile")
def check_profile(current_user: dict = Depends(require_teacher), db: Session = Depends(get_db)):
   
    # Check if a student record exists for this user_id
    teacher = db.query(models.Teacher).filter(models.Teacher.user_id == current_user.get("user_id")).first()
    return {"profile_completed": teacher is not None}


#1.3 to provide profile data to teacher on request
@app.get("/teacher/me", response_model=dtos.TeacherProfileOut)
def get_teacher_profile(current_user: dict = Depends(require_teacher), db: Session = Depends(get_db)):
   
    # 1. Fetching the teacher roe object 
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


#1.4  It assigns batches to teachers
@app.post("/teacher/assign-batch")
def batch_assignment(batch_data: dtos.BatchAssign, 
                    current_user: dict = Depends(require_teacher), 
                    db: Session = Depends(get_db)
                    ):
    
    # 1. Fetch the teacher's row object
    teacher = db.query(models.Teacher).filter(models.Teacher.user_id == current_user.get("user_id")).first()
    if not teacher:
        raise HTTPException(status_code=404, detail="Teacher profile not found. Complete profile first.")

    # 2.Normalizing batch name (e.g., " cs-2026 " -> "CS-2026") to prevent case/space duplicates
    clean_batch_name = batch_data.batch_name.strip().upper()

    # 3. Get-or-Create in BATCHES table
    batch = db.query(models.Batch).filter(models.Batch.batch_name == clean_batch_name).first()
    if not batch:
        batch = models.Batch(batch_name=clean_batch_name)
        db.add(batch)
        db.commit()
        db.refresh(batch)  # Fetches the auto-generated batch.id

    # 4. Prevent duplicate linking in TEACHER_BATCHES
    existing_link = db.query(models.TeacherBatch).filter_by(
        teacher_id=teacher.id, 
        batch_id=batch.id
    ).first()
    
    if existing_link:
        raise HTTPException(status_code=409, detail="You are already assigned to this batch")

    # 5. Link teacher and batch in junction table
    new_link = models.TeacherBatch(teacher_id=teacher.id, batch_id=batch.id)
    db.add(new_link)
    db.commit()

    return {"message": f"Batch '{batch.batch_name}' assigned successfully!", "batch_id": batch.id, "batch_name": batch.batch_name}
    
    
#1.5 Returns all batches linked to teacher during quiz creations
@app.get("/teacher/my-batches", response_model=List[dtos.BatchOut])
def linked_batches(current_user: dict = Depends(require_teacher), 
                   db: Session = Depends(get_db)):
 
    # 1. Fetching teacher row object
    teacher = db.query(models.Teacher).filter(models.Teacher.user_id == current_user.get("user_id")).first()
    if not teacher:
        return []

    # 2. SQL JOIN: Fetch Batch details linked to this teacher via TeacherBatch
    batches = db.query(models.Batch).join(
        models.TeacherBatch, models.Batch.id == models.TeacherBatch.batch_id
    ).filter(
        models.TeacherBatch.teacher_id == teacher.id
    ).all()

    return batches

    
# @app.post("/create-quiz") ---> generate_preview ---> /save_quiz (to allow teacher to see the quiz if he assured with it can save in db)

#2.1 (generation of quiz through llm asynchronously)
@app.post("/generate_preview")
async def generate_quiz(
    batch_id: int = Form(...),
    topic: str = Form(...),
    num_questions: int = Form(...),
    generation_mode: str = Form(...),
    start_page: Optional[int] = Form(None), # Optional kyunki sirf method 2 me aayega
    end_page: Optional[int] = Form(None),   # Optional kyunki sirf method 2 me aayega
    file: Optional[UploadFile] = File(None),
    current_user: dict = Depends(teacher_batch_ownership),
    db: Session = Depends(get_db)
):  
    # authenticationa & RBAC already handled by :-check_teacher_authority         
    
    # 1. Extract File Bytes (If uploaded)
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
def save_quiz(quiz_to_save:dtos.QuizSaveSchema, teacher = Depends(teacher_BatchAndQuiz_ownership), db: Session = Depends(get_db)):

        # authenticationa & RBAC already handled by :-check_teacher_authority         
            
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

#3 all quizzes created by teacher till date
@app.get("/my-quizzes",response_model=List[dtos.TeacherOwnQuiz])
def get_my_quizzes(current_user: dict = Depends(require_teacher), db: Session = Depends(get_db)):
   
    # 1. Current teacher ko DB me dhoondho
    teacher = db.query(models.Teacher).filter(models.Teacher.user_id== current_user.get("user_id")).first()
    if not teacher:
        return []
    
    # SQL Join: 
    quizzes = db.query(
        models.Quiz.id,
        models.Quiz.title,
        models.Batch.batch_name
    ).join(
        models.Batch, models.Quiz.batch_id == models.Batch.id
    ).filter(
        models.Quiz.teacher_id == teacher.id
    ).all()
    
    return quizzes

# 4. LEADERBOARD API (Teacher API)
@app.get("/quiz/{quiz_id}/leaderboard", response_model=dtos.LeaderboardResponse)
def get_leaderboard(quiz_id: int, current_user = Depends(teacher_BatchAndQuiz_ownership), db: Session = Depends(get_db)):

    # 1. SQL Join & Sort: Attempts aur Users table ko jodna aur highest score upar rakhna
    leaderboard_data = db.query(
        models.Student.student_name, 
        models.Attempt.score
    ).join(models.Attempt, models.Student.id == models.Attempt.student_id)\
     .filter(models.Attempt.quiz_id == quiz_id)\
     .order_by(desc(models.Attempt.score)).all()
    
    return {"quiz_id": quiz_id, "leaderboard": leaderboard_data}

# ==========================================
# STUDENT APIs
# ==========================================

# 1.0 fetching all batches available to let student decide their own batch
@app.get("/all-batches",response_model=List[dtos.BatchOut])
def get_batches(current_user:dict=Depends(require_student),
                db: Session= Depends(get_db)):
   
    # 1. Fetch all available batches, sorted alphabetically for a clean UI dropdown
    batches = db.query(models.Batch).order_by(models.Batch.batch_name).all()

    return batches

# 1.1 student profile data saving in db
@app.post("/student/complete_profile")
def complete_profile(profile: dtos.StudentProfileCreate, current_user: dict = Depends(require_student), db: Session = Depends(get_db)):
    #check for already saved profile
    user_id=current_user.get("user_id")
    existing_student = db.query(models.Student).filter(models.Student.user_id == user_id).first()
    if existing_student:
        raise HTTPException(status_code=409, detail="Profile already exists!")
    
    # Verifying the batch_id actually exists in the 'batches' table before inserting
    batch_exists = db.query(models.Batch).filter(models.Batch.id == profile.batch_id).first()
    if not batch_exists:
        raise HTTPException(status_code=404, detail="Selected batch does not exist")
        
    #  Create the domain record linking to the auth user_id
    new_student = models.Student(
        user_id=user_id,
        student_name=profile.student_name,
        email=profile.email,
        contact=profile.contact,
        batch_id=profile.batch_id
    )
    
    db.add(new_student)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="That email or contact number is already in use")
    
    return {"message": "Profile completed successfully!"}

#1.2 checking the profile complete before accessing other services
@app.get("/student/check_profile")
def check_profile(current_user: dict = Depends(require_student), db: Session = Depends(get_db)):
    
    # Check if a student record exists for this user_id
    student = db.query(models.Student).filter(models.Student.user_id == current_user.get("user_id")).first()
    return {"profile_completed": student is not None}

#1.3 provide the profile data to student on request
@app.get("/student/me", response_model=dtos.StudentProfileOut)
def get_student_profile(current_user: dict = Depends(require_student), db: Session = Depends(get_db)):

    # SQL Join: Fetching student details
    result = db.query(
        models.Student.student_name,
        models.Student.email,
        models.Student.contact,
        models.Batch.batch_name
    ).join(
        models.Batch, models.Student.batch_id == models.Batch.id
    ).filter(
        models.Student.user_id == current_user.get("user_id")
    ).first()
    
    if not result:
        raise HTTPException(status_code=404, detail="Profile not found")
        
    return {
        "name": result.student_name,
        "email": result.email,
        "contact": result.contact,
        "batch_name": result.batch_name 
    }

# 2 AVAILABLE QUIZZES (Batch based filtering)
@app.get("/available-quizzes", response_model=List[dtos.AvailableQuizOut])
def get_available_quizzes(current_user: dict = Depends(require_student), db: Session = Depends(get_db)):

    # 1. extracting the Student ID & batch
    student = db.query(models.Student).filter(models.Student.user_id == current_user.get("user_id")).first()
    if not student:
        return [] # Returns an empty list 

    # 2. Subquery: Wo saari Quiz IDs, that student has already attempted
    attempted_quiz_ids = db.query(models.Attempt.quiz_id).filter(models.Attempt.student_id == student.id)

    # 3. Main Query: Batch match karo AUR (~in_) filter lagao ki ID attempted list me NA ho
    available_quizzes = db.query(models.Quiz).filter(
             models.Quiz.batch_id == student.batch_id,
             ~models.Quiz.id.in_(attempted_quiz_ids)  # '~' ka matlab SQL me NOT hota hai
        ).all()
    
    return available_quizzes

# 3. GET QUIZ BY ID (For attempting the quiz - Hides correct answers)
@app.get("/quiz/{quiz_id}", response_model=dtos.QuizSentDB)
def get_quiz_to_attempt(quiz_id: int, student = Depends(check_student_authority), db: Session = Depends(get_db)):

    quiz=db.query(models.Quiz).filter(models.Quiz.id==quiz_id).first()
    
    questions = db.query(models.Question).filter(models.Question.quiz_id == quiz_id).all()
    
    #  Pydantic khud 'correct_answer' hata dega.
    return {"quiz_title": quiz.title, "questions": questions}

# 4. SUBMIT QUIZ & EVALUATION ENGINE
@app.post("/submit-quiz", response_model=dtos.SubmitQuizResponse)
def submit_quiz(submission: dtos.QuizSubmit, student = Depends(check_student_authority), db: Session = Depends(get_db)):
    # Authenticationa & TBAC already handled by check_student_authority
    
    # Check if student already submitted this quiz
    #"Double Submit" ya "Race Condition" kehte hain,network slow hone ki wajah se request retry ho jate hai
    existing_attempt = db.query(models.Attempt).filter_by(
        student_id=student.id, 
        quiz_id=submission.quiz_id
    ).first()
    
    if existing_attempt:
        raise HTTPException(status_code=409, detail="You have already attempted this quiz!")

    #  Database se saare questions ek baar me fetch kar lo
    db_questions = db.query(models.Question).filter(models.Question.quiz_id == submission.quiz_id).all()
    
    # storing the student answer in map to prevent duplicate answer injection with all options 
    answers = {a.question_id: a.selected_option for a in submission.answers}
    score = sum(1 for q in db_questions if answers.get(q.id) == q.correct_answer)      
    
    # Score DB me save karo
    attempt = models.Attempt(student_id=student.id, quiz_id=submission.quiz_id, score=score)
    db.add(attempt)
    db.commit()
    
    return {"message": "Quiz submitted Successfully!",
            "total_Questions": len(db_questions),
            "score": score}

# 5. MY SCORES API (Student)
@app.get("/my-scores", response_model=List[dtos.ScoreResponse])
def get_my_scores(current_user: dict = Depends(require_student), db: Session = Depends(get_db)):
      
    student = db.query(models.Student).filter(models.Student.user_id == current_user.get("user_id")).first()
    if not student:
        return []
    
    # 1. SQL Join: Attempts aur Quiz table ko jodna
    scores_data = db.query(
        models.Attempt.quiz_id,
        models.Quiz.title.label("quiz_title"),
        models.Attempt.score
    ).join(models.Quiz, models.Attempt.quiz_id == models.Quiz.id)\
     .filter(models.Attempt.student_id == student.id).all()
    
    # FastAPI aur Pydantic automatically is data ko List[ScoreResponse] me format kar denge
    return scores_data


@app.get("/")
def health_check():
    return {"status": "ok"}