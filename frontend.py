# for frontend and making http request
import streamlit as st
#act as http client, allows to make http requests
import requests
import time # for freezing the screen for showing success msg before rerun

#for extracting the claims form jwt token
from jose import jwt

# to load fastapi backend url from.env
import os
from dotenv import load_dotenv
load_dotenv()
#Frontend -> Backend Endpoint
API_URL = os.getenv("API_URL")

# Ye variables browser refresh hone par bhi data store rakhenge
if "token" not in st.session_state:
    st.session_state.token = None
    st.session_state.role = None

# ==========================================
# 1. AUTHENTICATION UI (Login / Register)
# ==========================================
def auth_page():
    st.title("AI Quiz Management System")
    
    # st.tabs use karke Login/Signup ko separate kiya hai
    tab1, tab2 = st.tabs(["Login", "Signup"])
    
    # --- LOGIN TAB ---
    with tab1:
        # st.form ensures ki har letter type karne par page reload na ho
        with st.form("login_form"):
            st.subheader("Login to your account")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login")
            
            if submitted:
                # FastAPI ka OAuth2PasswordRequestForm form-data expect karta hai, JSON nahi
                login_data = {"username": username, "password": password}
                response = requests.post(f"{API_URL}/login", data=login_data)
                
                if response.status_code == 200:
                    data = response.json() # .json() converts json format to python dictonary or list
                    # Token aur role ko session state me save karo
                    st.session_state.token = data["access_token"]

                    # Token ke payload ko bina secret key ke decode karna
                    payload = jwt.get_unverified_claims(data["access_token"])
                
                    st.session_state.role =payload.get("role")
                    st.success("Login Successful!")
                    st.rerun() # Page refresh karo taaki dashboard open ho sake
                else:
                    st.error("Invalid username or password")

    # --- SIGNUP TAB ---
    with tab2:
        with st.form("signup_form"):
            st.subheader("Create a new account")
            new_user = st.text_input("Username")
            new_pass = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["student", "teacher"])
            registered = st.form_submit_button("Signup")
            
            if registered:
                reg_data = {
                    "username": new_user,
                    "password": new_pass,
                    "role": role
                }
                response = requests.post(f"{API_URL}/register", json=reg_data)
                
                if response.status_code == 200:
                    st.success("Account created successfully! Please go to the Login tab.")
                else:
                    # 1. Check if the server explicitly sent JSON
                    is_json = "application/json" in response.headers.get("Content-Type", "")
                    # 2. Extract cleanly based on the type
                    error_msg = response.json().get("detail") if is_json else response.text
                    st.error(f"Error: {error_msg}")

# ==========================================
# 2. student dashboard
# ==========================================

def student_dashboard():

    # Har protected API call me token bhejenge is header ke through
    headers = {"Authorization": f"Bearer {st.session_state.token}"}
    
    # profile checking before moving to other features
    if "student_profile" not in st.session_state:
        status_res = requests.get(f"{API_URL}/student/check_profile", headers=headers)
        
        if status_res.status_code == 200:
            st.session_state.student_profile= status_res.json().get("profile_completed", False)
        else:
            st.session_state.student_profile= False
    
    # --- Profile completion form ---
    if not st.session_state.student_profile:
        st.info("Welcome! Please complete your student profile to access quizzes.")
        
        with st.form("profile_setup_form"):
            st.write("### Profile Setup")
            name = st.text_input("Full Name")
            email = st.text_input("Email Address")
            contact = st.text_input("Contact Number")
            batch = st.text_input("Batch ID (e.g., BATCH-01)")
            
            submit_profile = st.form_submit_button("Save Profile")
            
            if submit_profile:
                payload = {
                    "student_name": name,
                    "email": email,
                    "contact": contact,
                    "batch_id": batch
                }
                res = requests.post(f"{API_URL}/student/complete_profile", json=payload, headers=headers)
                
                # Success: Profile created
                if res.status_code == 200:
                    st.success("Profile saved successfully!")
                    st.session_state.student_profile= True
                    time.sleep(1)
                    st.rerun()
                    
                # safety guard: agar internet drop or double click by user then it will handle it and prevent infite loop since before the first save success msg this request  sent and make variable true in next line.
                elif res.status_code == 400 and "already exists" in res.text.lower():
                    st.session_state.student_profile = True
                    st.rerun()
                    
                else:
                    st.error(res.json().get("detail", "Error saving profile"))
                    
        # Stop executing the rest of the page until they pass the gate
        st.stop()

    st.sidebar.title("Student Panel")
    page = st.sidebar.radio(
        "Navigation", 
        ["👤 My Profile", "📚 Live Quizzes", "🏆 My Scores"]
    )

    # Bottom-aligned Logout
    st.sidebar.markdown("<br><br><br><br><br>", unsafe_allow_html=True)
    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.token = None
        st.session_state.role = None
        if "profile_data" in st.session_state:
            del st.session_state.profile_data
        if "active_quiz_id" in st.session_state:
            del st.session_state.active_quiz_id    
        st.rerun()
    

    # --- PAGE: MY PROFILE ---
    if page == "👤 My Profile":
        st.subheader("My Profile")
        
        if "profile_data" not in st.session_state:
            with st.spinner("Loading profile..."):
                res = requests.get(f"{API_URL}/student/me", headers=headers)
                if res.status_code == 200:
                    st.session_state.profile_data = res.json()
                else:
                    st.error("Failed to load profile")
                    
        if "profile_data" in st.session_state:
            p = st.session_state.profile_data
            st.info(f"👤 **Name:** {p.get('name', 'N/A')}")
            st.info(f"📧 **Email:** {p.get('email', 'N/A')}")
            st.info(f"📞 **Contact:** {p.get('contact', 'N/A')}")
            st.info(f"🏫 **Batch Id:** {p.get('batch_id', 'N/A')}")

    
    # ---  LIVE QUIZZES ---
    elif page  == "📚 Live Quizzes":
        st.subheader("Available Quizzes")

        # AGAR QUIZ ACTIVE NAHI HAI, TOH SIRF DROPDOWN DIKHAO
        if not st.session_state.get("active_quiz_id"):
            # API call to get quizzes not yet attempted
            response = requests.get(f"{API_URL}/available-quizzes", headers=headers)
            
            if response.status_code == 200:
                quizzes = response.json()
                if not quizzes:
                    st.info("No new quizzes available for your batch.")
                else:
                    # Quiz select karne ke liye dropdown
                    quiz_options = {q['title']: q['id'] for q in quizzes}
                    selected_quiz_title = st.selectbox("Select a Quiz to Attempt", list(quiz_options.keys()))
                
                    if st.button("Start Quiz"):
                        # Save selected quiz ID in session to show the questions
                        st.session_state.active_quiz_id = quiz_options[selected_quiz_title]
                        st.rerun()
            else:
                st.error(f"API Error: {response.status_code} - {response.text}")
        
        # --- RENDER THE QUIZ FORM IF A QUIZ IS SELECTED ---
        else:
            quiz_id = st.session_state.active_quiz_id
            quiz_response = requests.get(f"{API_URL}/quiz/{quiz_id}", headers=headers)
            
            if quiz_response.status_code == 200:
                quiz_data = quiz_response.json()
                st.write(f"### {quiz_data['quiz_title']}")
                
                with st.form("quiz_attempt_form"):
                    student_answers = []
                    
                    # Loop through questions and render radio buttons
                    for q in quiz_data['questions']:
                        st.markdown(f"**Q: {q['question_text']}**")
                        # Radio button returns the selected string
                        selected_opt = st.radio("Options", q['options'], index=None, key=f"q_{q['id']}")
                        
                        student_answers.append({
                            "question_id": q['id'],
                            "selected_option": selected_opt
                        })
                        st.divider() # Ek line draw karega visual separation ke liye
                        
                    submit_quiz = st.form_submit_button("Submit Answers")
                    
                    if submit_quiz:
                        payload = {
                            "quiz_id": quiz_id,
                            "answers": student_answers
                        }
                        # API call to submit answers
                        submit_res = requests.post(f"{API_URL}/submit-quiz", json=payload, headers=headers)
                        
                        if submit_res.status_code == 200:
                            score_data = submit_res.json()
                            st.success(f"Quiz Submitted! Your score: {score_data['score']} / {score_data['total_Questions']}")
                            # freezes screen so user can see score
                            time.sleep(2)
                        # Catch the "already submitted" error from the backend
                        elif submit_res.status_code == 400 and "already" in submit_res.text.lower():
                            st.warning("You have already submitted this quiz!")
                        else:
                            st.error(submit_res.json().get("detail", "Error submitting quiz"))
            else:
                st.error("Failed to load quiz details.")
                if st.button("⬅ Back"):
                    st.session_state.active_quiz_id = None
                    st.rerun()


            # Clear the active quiz so it returns to the selection screen
            st.write("---")
            if st.button("⬅ Back to Available Quizzes"):
                st.session_state.active_quiz_id = None
                st.rerun()         

    # --- MY SCORES ---
    elif page =="🏆 My Scores":
        st.subheader("My Performance")
        score_res = requests.get(f"{API_URL}/my-scores", headers=headers)
        
        if score_res.status_code == 200:
            scores = score_res.json()
            if scores:
                # Streamlit automatically renders list of dicts as a interactive table,allows users to scroll, resize, and click column headers to sort the data.
                st.dataframe(scores, use_container_width=True, hide_index=True)
                #use_container_width=True-forces the grid to stretch to 100% of the available screen or column width.
                #hide_index=True: Hides the default system row numbers (0, 1, 2)
            else:
                st.info("You haven't attempted any quizzes yet.")

# ==========================================
# 3. Teacher Dashboard
# ==========================================

def teacher_dashboard():
    
    # Logout Button
    col1, col2 = st.columns([8, 1]) #col1 is left empty to work as spacer to place logout button in the extreme right 
    with col2:
        if st.button("Logout"):
            st.session_state.token = None
            st.session_state.role = None
            st.rerun()

    headers = {"Authorization": f"Bearer {st.session_state.token}"}

    # profile checking before moving to other features
    if "teacher_profile" not in st.session_state:
        status_res = requests.get(f"{API_URL}/teacher/check_profile", headers=headers)
            
        if status_res.status_code == 200:
            st.session_state.teacher_profile = status_res.json().get("profile_completed", False)
        else:
            st.session_state.teacher_profile = False
        
    # --- Profile completion form ---
    if not st.session_state.teacher_profile:
        st.info("Welcome! Please complete your teacher profile to access features.")
            
        with st.form("profile_setup_form"):
            st.write("### Profile Setup")
            name = st.text_input("Full Name")
            email = st.text_input("Email Address")
            contact = st.text_input("Contact Number")
            department= st.text_input("Department Name")
                
            submit_profile = st.form_submit_button("Save Profile")
                
            if submit_profile:
                payload = {
                    "teacher_name": name,
                    "email": email,
                    "contact": contact,
                    "department": department
                }
                
                res = requests.post(f"{API_URL}/teacher/complete_profile", json=payload, headers=headers)
                    
                # Success: Profile created
                if res.status_code == 200:
                    st.success("Profile saved successfully!")
                    st.session_state.teacher_profile = True
                    time.sleep(1)
                    st.rerun()
                        
                # Catch the returning user edge-case!
                elif res.status_code == 400 and "already exists" in res.text.lower():
                    st.session_state.teacher_profile= True
                    st.rerun()
                        
                else:
                    st.error(res.json().get("detail", "Error saving profile"))
                        
        # Stop executing the rest of the page until they complete profile
        st.stop()# Stops sidebar and main content from loading!

    #options
    st.sidebar.title("Teacher Panel")
    page = st.sidebar.radio(
        "Navigation", 
        ["👤 My Profile","📝 Create Quiz", "📚 My Quizzes", "🏆 Leaderboard"]
    )

    # Bottom-aligned Logout
    st.sidebar.markdown("<br><br><br><br><br>", unsafe_allow_html=True)
    st.sidebar.divider()
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.token = None
        st.session_state.role = None
        if "preview_quiz" in st.session_state:
            del st.session_state.preview_quiz
        if "profile_data" in st.session_state:
            del st.session_state.profile_data
        st.rerun()

    # --- PAGE: MY PROFILE ---
    if page == "👤 My Profile":
        st.subheader("Profile")
        
        if "profile_data" not in st.session_state:
            with st.spinner("Loading profile..."):
                res = requests.get(f"{API_URL}/teacher/me", headers=headers)
                if res.status_code == 200:
                    st.session_state.profile_data = res.json()
                else:
                    st.error("Failed to load profile")
                    
        if "profile_data" in st.session_state:
            p = st.session_state.profile_data
            st.info(f"👤 **Name:** {p.get('name', 'N/A')}")
            st.info(f"📧 **Email:** {p.get('email', 'N/A')}")
            st.info(f"📞 **Contact:** {p.get('contact', 'N/A')}")
            st.info(f"🏫 **Department:** {p.get('department', 'N/A')}")
    
   
    # --- TO CREATE QUIZ ---
    elif page == "📝 Create Quiz":
        st.subheader("Generate Quiz With AI")
        
        # 1. UI Reactivity: Radio button st.form ke BAHAR hona chahiye.
        # Agar ye form ke andar hoga, toh change karne par UI turant update nahi hoga (kyunki form re-render block karta hai).
        mode_selection = st.radio(
            "Select Generation Mode", 
            ["General Topic", "Generate from Study Material (PDF)", "Extract from Quiz Paper (PDF)"],
            horizontal=True
        )
        
        mode_map = {
            "General Topic": "general_topic",
            "Generate from Study Material (PDF)": "generate_from_content",
            "Extract from Quiz Paper (PDF)": "extract_from_quiz"
        }
        selected_api_mode = mode_map[mode_selection]

        # container to hold the quiz, to show preview to the teacher
        if "preview_quiz" not in st.session_state:
            st.session_state.preview_quiz=None

        with st.form("Create Quiz"):
            col_a, col_b = st.columns(2)
            with col_a:
                batch_id = st.text_input("Batch ID (e.g., CS-2026)")
                num_questions = st.number_input("Number of Questions", min_value=1, max_value=50, value=5)
            with col_b:
                topic = st.text_input("Topic")

            # external file upload varibale for other 2 path of generation
            uploaded_file = None
            start_page, end_page = None, None   

            if selected_api_mode != "general_topic":
                uploaded_file = st.file_uploader("Upload PDF Document", type=["pdf"])
            
            if selected_api_mode == "generate_from_content":
                    st.caption("Select Page Range for quiz creation")
                    col_p1, col_p2 = st.columns(2)
                    with col_p1:
                        start_page = st.number_input("Start Page", min_value=1, value=1)
                    with col_p2:
                        end_page = st.number_input("End Page", min_value=1, value=1)

            submit_btn = st.form_submit_button("Generate Quiz")
            
            if submit_btn:
                if not batch_id or not topic:
                    st.error("Batch ID and Topic are required!")
                elif selected_api_mode != "general_topic" and uploaded_file is None:
                    st.error("Please upload a PDF file for this generation mode.")
                elif selected_api_mode == "generate_from_content" and (start_page > end_page or start_page is None or end_page is None) :
                    st.error("Start Page or end_page is either incorrect or missing")
                else:
                    with st.spinner("LangChain is processing... Please wait."):
                        # 3. HTTP Multipart Request Preparation
                        payload_data = {
                            "batch_id": batch_id,
                            "num_questions": num_questions,
                            "topic": topic,
                            "generation_mode": selected_api_mode
                        }
                        
                        payload_files = None

                        # method 2 of creation require trimming for better quiz creation and avoiding hallucination
                        if selected_api_mode == "generate_from_content":
                            payload_data["start_page"] = start_page
                            payload_data["end_page"] = end_page

                        if uploaded_file is not None:
                            # (filename, file_bytes, content_type) format for requests
                            payload_files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
                        
                        # API Call (FastAPI will extract via Form and File)
                        response = requests.post(
                            f"{API_URL}/generate_preview", 
                            data=payload_data,   # Maps to FastAPI Form(...)
                            files=payload_files, # Maps to FastAPI File(...) - Triggers multipart/form-data
                            headers=headers
                        )
                        
                        if response.status_code == 200:
                            st.session_state.preview_quiz={
                                "batch_id": batch_id,
                                "topic": topic,
                                 "questions": response.json()["questions"]
                                 }
                            st.success("Preview Generated! Scroll down to verify.")
                        else:
                            st.error(f"Error: {response.text}")
            
        if st.session_state.preview_quiz:
            st.divider()
            st.subheader("Review Quiz Before Saving")
            serial_count=1

            for q in st.session_state.preview_quiz['questions']:
                st.markdown(f"**Q:{serial_count} {q['question_text']}**")
                # Radio button for options
                st.radio("Options", q['options'],index=None, key=f"preview_opt{serial_count}")
                st.markdown(f"Correct Answer : {q['correct_answer']}")                                        
                st.divider() # Ek line draw karega visual separation ke liye
                serial_count+=1
                    
            save_btn = st.button("Save Quiz")

            if save_btn:
                response=requests.post(f"{API_URL}/save_quiz", json=st.session_state.preview_quiz, headers=headers)

                if response.status_code == 200:
                    st.success("Quiz saved successfully in Database!")
                    # Save hone ke baad memory clean kardo taaki screen clear ho jaye
                    st.session_state.preview_quiz = None
                    # 3 second wait karo taaki user success message dekh sake
                    time.sleep(3)
                    st.rerun()
                else:
                    st.error(f"Failed to save: {response.text}")

    # --- myy_quizzes- teacher's own created quizes---
    elif page == "📚 My Quizzes":
        st.subheader("Your Quizes ")
        
        total_quiz = requests.get(f"{API_URL}/my-quizzes", headers=headers)
            
        if total_quiz.status_code == 200:
            quizzes = total_quiz.json()
            if quizzes:
                st.dataframe(quizzes)
            else:
                st.info("You haven't created any quizzes yet.")
        else:
            st.error(f"Failed to fetch quizzes: {total_quiz.text}")
                        
                       
    # ---  LEADERBOARD ---
    elif page == "🏆 Leaderboard":
        st.subheader("Quiz Leaderboards")
        
        # API Call 1: Fetch quizzes to populate the dropdown
        quiz_res = requests.get(f"{API_URL}/my-quizzes", headers=headers)
        
        if quiz_res.status_code == 200:
            quizzes = quiz_res.json()
            if quizzes:
                quiz_options = {f"{q['title']} (Batch: {q['batch_id']})": q['id'] for q in quizzes}
                
                # Align dropdown and button horizontally
                col_a, col_b = st.columns([3, 1])
                with col_a:
                    selected_quiz_label = st.selectbox("Select a Quiz", list(quiz_options.keys()))
                with col_b:
                    st.write("") # Vertical spacing trick to align button with input
                    st.write("")
                    view_btn = st.button("Get Leaderboard")
                
                if view_btn:
                    selected_id = quiz_options[selected_quiz_label]
                    
                    # API Call 2: Fetch the actual leaderboard data
                    lb_res = requests.get(f"{API_URL}/quiz/{selected_id}/leaderboard", headers=headers)
                    
                    if lb_res.status_code == 200:
                        lb_data = lb_res.json()
                        leaderboard_list = lb_data.get("leaderboard", [])
                        
                        if leaderboard_list:    
                            formatted_data = []
                            for index, user_info in enumerate(leaderboard_list):
                                # Rank suffix logic (1st, 2nd, 3rd, 4th...)
                                rank = index + 1
                                if 11 <= (rank % 100) <= 13:
                                    suffix = 'th'
                                else:
                                    suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(rank % 10, 'th')
                                
                                formatted_data.append({
                                    "RANK": f"{rank}{suffix}",
                                    "NAME": user_info.get("username", "").title(),
                                    "SCORE": user_info.get("score", 0) 
                                })
                            
                            # 2. Convert to DataFrame for rendering interactive table
                            st.dataframe(formatted_data,use_container_width=True, hide_index=True)
                        else:
                            st.info("No students have attempted this quiz yet.")
                    else:
                       st.error(lb_res.json().get("detail", "Failed to fetch leaderboard."))
            else:
                st.info("You are yet to create any quiz")

# ==========================================
#  4.program comes here first---ROUTING LOGIC
# ==========================================

if st.session_state.token is None:
    auth_page()
elif st.session_state.role == "teacher":
    teacher_dashboard()
elif st.session_state.role == "student":
    student_dashboard()
    