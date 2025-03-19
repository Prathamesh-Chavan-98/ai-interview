from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import os
from functools import wraps
import fitz
from groq import Groq
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional
import json

app = Flask(__name__)
app.secret_key = 'VcBmObhWevILyRpnSMwTb+KBSy3fSKhEycyfgixsXXk='  # Change this in production

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Initialize Groq client
client = Groq(api_key='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')  # Replace with your API key

# Database mockup (replace with real database in production)
class MockDB:
    def __init__(self):
        self.users: Dict = {
            'businesses': {},
            'candidates': {}
        }
        self.job_requirements: Dict = {}
        self.interviews: Dict = {}
        
    def save_user(self, user_type: str, username: str, password: str) -> bool:
        if username in self.users[user_type]:
            return False
        self.users[user_type][username] = {
            'password': password,
            'created_at': datetime.now(),
            'profile': {}
        }
        return True
    
    def get_user(self, user_type: str, username: str) -> Optional[Dict]:
        return self.users[user_type].get(username)
    
    def save_job_requirement(self, business_id: str, requirements: str) -> str:
        job_id = f"job_{len(self.job_requirements) + 1}"
        self.job_requirements[job_id] = {
            'business_id': business_id,
            'requirements': requirements,
            'created_at': datetime.now()
        }
        return job_id
    
    def save_interview(self, candidate_id: str, job_id: str, answers: List[Dict]) -> str:
        interview_id = f"interview_{len(self.interviews) + 1}"
        self.interviews[interview_id] = {
            'candidate_id': candidate_id,
            'job_id': job_id,
            'answers': answers,
            'created_at': datetime.now()
        }
        return interview_id

db = MockDB()

# Helper functions
def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in first.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def extract_text_from_pdf(pdf_path: str) -> str:
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text()
        return text
    except Exception as e:
        print(f"Error extracting PDF text: {e}")
        return ""

def get_groq_response(prompt: str) -> str:
    try:
        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile"
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"Error getting Groq response: {e}")
        return ""

def generate_questions(resume_text: str, skills: str, requirements: str) -> List[str]:
    prompt = f"""
    - Resume Content: {resume_text}
    - Skills: {skills}
    - business_requirements: {requirements}

    You are a professional AI interviewer tasked with generating **10 highly relevant, realistic, and knowledge-assessing** interview questions based on a candidate's resume, projects, skills, and areas of interest.
    Ask questions on Resume Content: {resume_text}
    Ask questions on Skills: {skills}
    Ask questions on business_requirements: {requirements}

    Generate moderate level questions on the project, keep the language of questions easy, and include the project name if available while asking questions.
    ask 4 questions on Resume Content
    ask 3 questions on Skills
    ask 3 questions on business_requirements
    Strictly generate 10 only questions and no other word, only pure questions.
    """
    
    questions = get_groq_response(prompt).strip().split('\n')
    return [q for q in questions if q.strip()]

def evaluate_answer(question: str, answer: str) -> Dict:
    prompt = f"""
    Evaluate this interview answer professionally:
    Question: {question}
    Answer: {answer}

    Provide:
    1. Score (0-10)
    2. Brief, constructive feedback
    
    Format: JSON object with 'score' and 'feedback' keys
    """
    evaluation = get_groq_response(prompt)
    print(evaluation)
    cleaned_string = evaluation.strip('```json\n').strip('```')
    result = json.loads(cleaned_string)
    print(cleaned_string)
    return {
        'score': result.get('score', 0),
        'feedback': result.get('feedback', 'No feedback available')
    }

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        user_type = request.form['user_type']
        username = request.form['username']
        password = request.form['password']  # In production, hash this!
        
        if db.save_user(user_type, username, password):
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        else:
            flash('Username already exists.', 'danger')
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_type = request.form['user_type']
        username = request.form['username']
        password = request.form['password']
        
        user = db.get_user(user_type, username)
        if user and user['password'] == password:  # Use proper password verification in production
            session['user_id'] = username
            session['user_type'] = user_type
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials.', 'danger')
    
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def dashboard():
    user_type = session['user_type']
    if user_type == 'businesses':
        return render_template('business_dashboard.html', 
                             job_requirements=db.job_requirements)
    else:
        return render_template('candidate_dashboard.html')

@app.route('/post_job', methods=['POST'])
@login_required
def post_job():
    if session['user_type'] != 'businesses':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    requirements = request.form['requirements']
    job_id = db.save_job_requirement(session['user_id'], requirements)
    flash('Job requirements posted successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/submit_profile', methods=['POST'])
@login_required
def submit_profile():
    if session['user_type'] != 'candidates':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    if 'resume' not in request.files:
        flash('No resume file uploaded.', 'danger')
        return redirect(url_for('dashboard'))
    
    file = request.files['resume']
    if file.filename == '':
        flash('No file selected.', 'danger')
        return redirect(url_for('dashboard'))
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        resume_text = extract_text_from_pdf(filepath)
        skills = request.form['skills']
        
        session['resume_text'] = resume_text
        session['skills'] = skills
        
        return redirect(url_for('interview'))
    
    flash('Invalid file type. Please upload a PDF.', 'danger')
    return redirect(url_for('dashboard'))

@app.route('/interview', methods=['GET', 'POST'])
@login_required
def interview():
    if session['user_type'] != 'candidates':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    if request.method == 'GET':
        if 'resume_text' not in session or 'skills' not in session:
            flash('Please submit your profile first.', 'warning')
            return redirect(url_for('dashboard'))
        
        # Get a random job requirement for demo (implement proper matching in production)
        job_id, job_data = next(iter(db.job_requirements.items()))
        session['job_id'] = job_id
        
        questions = generate_questions(
            session['resume_text'],
            session['skills'],
            job_data['requirements']
        )
        session['questions'] = questions
        
        return render_template('interview.html', questions=questions)
    
    return redirect(url_for('dashboard'))

@app.route('/submit_answers', methods=['POST'])
@login_required
def submit_answers():
    if 'questions' not in session:
        flash('No active interview session.', 'danger')
        return redirect(url_for('dashboard'))
    
    answers = []
    for i, question in enumerate(session['questions']):
        answer = request.form.get(f'answer_{i}')
        if answer:
            evaluation = evaluate_answer(question, answer)
            print(evaluation)
            answers.append({
                'question': question,
                'answer': answer,
                'score': evaluation['score'],
                'feedback': evaluation['feedback']
            })
    
    interview_id = db.save_interview(
        session['user_id'],
        session['job_id'],
        answers
    )
    
    session['current_interview'] = interview_id
    return redirect(url_for('results'))

@app.route('/results')
@login_required
def results():
    if 'current_interview' not in session:
        flash('No interview results available.', 'warning')
        return redirect(url_for('dashboard'))
    
    interview_data = db.interviews[session['current_interview']]
    evaluations = interview_data['answers']
    
    total_score = sum(eval['score'] for eval in evaluations)
    average_score = total_score / len(evaluations) if evaluations else 0
    
    return render_template('results.html',
                         evaluations=evaluations,
                         total_score=total_score,
                         average_score=average_score)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('index'))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)

