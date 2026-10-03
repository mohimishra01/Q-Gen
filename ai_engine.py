import pymupdf  # PyMuPDF for blazing fast PDF parsing
from pydantic import BaseModel, Field
from typing import List
from langchain_groq import ChatGroq
from langchain_core.prompts import ChatPromptTemplate

from dotenv import load_dotenv
load_dotenv()

# for duplicay check
import difflib
# for pydantic dtos used for llm output generation schema
import dtos


# 1. duplicay check fxn
# 1. duplicay check fxn (UPDATED for Backfill)
def deduplicate_llm_quiz(new_batch, existing_questions=None, threshold=0.8):
    if existing_questions is None:
        existing_questions = []
        
    accepted_questions = list(existing_questions) # Work on a copy of what we already have
    
    for new_q in new_batch:
        is_duplicate = False
        new_text = new_q['question_text'].lower()
        
        # Check against the ones we've already approved in previous loops
        for approved_q in accepted_questions:
            approved_text = approved_q['question_text'].lower()
            if difflib.SequenceMatcher(None, new_text, approved_text).ratio() >= threshold:
                is_duplicate = True
                break
                
        if not is_duplicate:
            accepted_questions.append(new_q)
            
    return accepted_questions

# 2. CONTEXT SLICING (No RAG)

def extract_text_from_pdf(file_bytes: bytes, start_page: int = None, end_page: int = None) -> str:
    if not file_bytes:
        return ""
    
    doc = pymupdf.open(stream=file_bytes, filetype="pdf")
    text = ""
    
    # UI bhejta hai 1-based index (e.g., Page 1), PyMuPDF use karta hai 0-based index.
    # Agar start_page nahi hai (None), toh 0 se shuru karo
    start_idx = (start_page - 1) if start_page else 0
    end_idx = end_page if end_page else len(doc)
    
    # Sirf selected range ke pages ko extract karo
    for i in range(start_idx, min(end_idx, len(doc))):
        text += doc[i].get_text() + "\n"
        
    doc.close()
    return text


# 3. SINGLE-PASS AI PIPELINE
async def generate_quiz_via_llm(mode: str, topic: str, count: int, file_bytes: bytes = None, start_page: int = None, end_page: int = None) -> List[dict]:
    # Temperature 0 rakhi hai taaki hallucination na ho, strictly facts par rahe
    llm = ChatGroq(model="openai/gpt-oss-120b", temperature=0)
    
    # LangChain ka sabse powerful method - forces output into our Pydantic schema
    structured_llm = llm.with_structured_output(dtos.LLMQuizOutput)
    
    context_text = ""
    if mode in ["generate_from_content", "extract_from_quiz"] and file_bytes:
        pdf_text = extract_text_from_pdf(file_bytes, start_page, end_page)

    # Dynamic Prompt Routing
    if mode == "general_topic":
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert educator. Generate exactly {count} diverse and challenging multiple-choice questions on the topic: '{topic}'.\n\n"
                       "FORMAT REQUIREMENT: Each question MUST have exactly 4 unique options total: exactly 1 correct answer and 3 plausible incorrect filler options (distractors).\n\n"
                       "QUALITY REQUIREMENT: Ensure the questions cover different aspects of the topic. Do not repeat the same concepts or rephrase the same question.\n\n"
                       "CRITICAL: You MUST use the provided extraction tool to return the data in a structured format. Do not output plain text.\n\n"),
            ("user", "Generate the quiz strictly following the format and quality constraints.")
        ])
    elif mode == "generate_from_content":
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are an expert educator. Create exactly {count} multiple choice questions about '{topic}'.\n"
                       "STRICT RULE: You must base your questions ONLY on the provided pdf text below. Do not use outside knowledge.\n"
                       "If the text does not contain information about '{topic}', return an empty list.\n\n"
                       "FORMAT REQUIREMENT: Each question MUST have exactly 4 unique options total: exactly 1 correct answer and 3 plausible incorrect filler options (distractors).\n\n"
                       "CRITICAL: You MUST use the provided extraction tool to return the data in a structured format. Do not output plain text.\n\n"
                       "Pdf Text:\n{pdf_text}"),
            ("user", "Generate the quiz strictly from the text, ensuring exactly 4 options per question.")
        ])
    else:  # extract_from_quiz
        prompt = ChatPromptTemplate.from_messages([
            ("system", "You are a highly accurate data extraction assistant. Your task is to extract exactly {count} questions specifically about '{topic}' from the provided Exam Text.\n\n"
               "STRICT TOPIC CHECK:\n"
               "Before extracting anything, verify if the Exam Text contains information related to the topic: '{topic}'.\n"
               "If the text is entirely unrelated to '{topic}', you MUST immediately return an empty list. Do NOT invent questions from outside knowledge.\n\n"
               "EXTRACTION RULES (Only if topic matches):\n"
               "1. IF the text already contains multiple-choice options: Extract those exact options and identify the correct one.\n"
               "2. IF the text ONLY provides the correct answer: You MUST generate 3 plausible but incorrect distractors to create a 4-option format.\n"
               "Ensure all 4 options are unique.\n\n"
               "CRITICAL: You MUST use the provided extraction tool to return the data in a structured format. Do not output plain text.\n\n"
               "Exam Text:\n{context_text}"),
            ("user", "Extract the quiz strictly following the topic check and tool format.")
        ])

    chain = prompt | structured_llm

    final_questions = []
    retries = 0
    max_retries = 2
    
    # Backfill loop: keep generating until we meet teacher requirement
    while len(final_questions) < count and retries < max_retries:
        deficit = count - len(final_questions)
        
        try:
            result = await chain.ainvoke({ #Asynchronous Invoke
                "count": deficit,
                "topic": topic,
                "context_text": context_text
            })
            
            new_batch = [q.model_dump() for q in result.questions] if result and result.questions else []
            
            # 2. duplicacy removal from  new batch against ALREADY accepted questions
            final_questions = deduplicate_llm_quiz(new_batch, existing_questions=final_questions)
            
        except Exception as e:
            print(f"LangChain Pipeline Error on retry {retries}: {e}")
            return []
            
        retries += 1
        
    if len(final_questions) < count:
        print(f"Warning: Only generated {len(final_questions)} unique questions after {max_retries} retries.")
        return []
        
    return final_questions

