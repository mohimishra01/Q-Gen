# DTO - Data Transfer Object.They strictly define how the data (payload) is transferred
# between the frontend and backend, without worrying about how it is stored in the database."
from pydantic import BaseModel,Field,ConfigDict
from typing import Optional,List

# new user creation schema for  transfer of data and validation
class NewUser(BaseModel):
    username: str
    password: str
    role: str

#student data transfer schema
class StudentProfileCreate(BaseModel):
    student_name: str
    email: str
    contact: str
    batch_id: str

class TeacherProfileCreate(BaseModel):
    teacher_name: str
    email: str
    contact: str
    department: str

# llm ko strictly output format specify krne ke liye
class QuestionCreate(BaseModel):
    question_text: str = Field(description="The actual quiz question")
    options: List[str] = Field(description="Exactly 4 multiple choice options")
    correct_answer: str = Field(description="The exact string of the correct option")
class LLMQuizOutput(BaseModel):
    questions: List[QuestionCreate]


# after preview the data is sent to db for saving- quiz data validation for storing in db
class QuestionSaveSchema(BaseModel):
    question_text: str
    options: List[str]
    correct_answer: str
class QuizSaveSchema(BaseModel):
    batch_id: str
    topic: str
    questions: List[QuestionSaveSchema]


# quiz questions sent to student format for transfer and validation
class QuestionSentDB(BaseModel):
    id: int
    question_text: str
    options: List[str]
    # correct_answer' field nahi hai, correct answers frontend par kabhi leak na hon.
class QuizSentDB(BaseModel):
    quiz_title: str
    questions: List[QuestionSentDB]
    
    #Modern Pydantic V2 syntax
    model_config = ConfigDict(from_attributes=True) 


# student attempted quiz-submission format
class StudentAnswer(BaseModel):
    question_id: int
    selected_option: str
class QuizSubmit(BaseModel):
    quiz_id: int
    answers: List[StudentAnswer]


# Student apne scores dekhega
class ScoreResponse(BaseModel):
    quiz_id: int
    quiz_title: str
    score: int

    model_config = ConfigDict(from_attributes=True)# SQLAlchemy gives Row objects, pydantic expects json data, from_attribute  and configdict tells pydantic how to handle row objects and inJect them into dictonaries (json)

    #Setting from_attributes=True inside ConfigDict tells Pydantic:"Hey, if you don't find a dictionary, try reading the data using dot notation like row.question_text."

class teacher_created_quizes(BaseModel):
    id: int
    title: str
    batch_id: str

    model_config = ConfigDict(from_attributes=True)