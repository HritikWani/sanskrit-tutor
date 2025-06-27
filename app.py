from flask import Flask, render_template, request, redirect, session, flash
from pymongo import MongoClient
import os
from datetime import datetime
import cloudinary
import cloudinary.uploader
from flask import abort
from bson.objectid import ObjectId
from functools import wraps
import bcrypt, random, smtplib
import re
from datetime import datetime, timedelta, timezone


#Cloudinary Config
cloudinary.config(
  cloud_name = os.getenv('CLOUDINARY_CLOUD_NAME'),
  api_key = os.getenv('CLOUDINARY_API_KEY'),
  api_secret = os.getenv('CLOUDINARY_API_SECRET')
)

#Flask App Config
app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')
app.config['MAX_CONTENT_LENGTH'] = 20 * 1024 * 1024  # 20MB max

@app.errorhandler(413)
def file_too_large(e):
    flash("File is too large. Max size is 10MB.")
    return redirect(request.url)

ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# MongoDB Config
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['sanskrit_tutor']
users_col = db['users']
students_col = db['students']
tests_col = db['tests']
schedules_col = db['schedules']
answers_col = db['answers']


# Helpers and Decorators
def login_required(role):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if session.get('role') != role:
                return redirect('/login')
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

def login_required_any(*roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session or session['role'] not in roles:
                flash("Unauthorized access.")
                return redirect('/login')
            return f(*args, **kwargs)
        return decorated_function
    return wrapper

def get_ist_today_range():
    """Returns start and end datetime of current day in IST timezone."""
    utc_now = datetime.utcnow()
    ist_now = utc_now + timedelta(hours=5, minutes=30)
    start_ist = datetime.combine(ist_now, datetime.min.time())
    end_ist = datetime.combine(ist_now, datetime.max.time())
    return ist_now, start_ist, end_ist

def get_student(student_id):
    return students_col.find_one({"student_id": student_id})

def is_strong_password(password):
    if (len(password) < 8 or
        not re.search(r"[A-Z]", password) or
        not re.search(r"[a-z]", password) or
        not re.search(r"\d", password) or
        not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password)):
        return False
    return True

metadata=db.metadata.find_one({"_id": "config"})

# ---------------Home------------------- #
@app.route('/')
def home():
    if 'role' in session:
        if session['role'] == 'admin': return redirect('/admin/dashboard')
        elif session['role'] == 'student': return redirect('/student/dashboard')
    return redirect('/login')

# ---------------- LOGIN ---------------- #
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username'].strip()
        password = request.form['password'].strip()
        if not username or not password:
            flash("Username and password are required.")
            return redirect('/login')

        u = users_col.find_one({"username": username})
        if u and bcrypt.checkpw(password.encode(), u['password']):
            # Update last login timestamp
            today, *_ =get_ist_today_range()
            users_col.update_one(
                {"_id": u['_id']},
                {"$set": {"last_login": today}}
            )
            session['username'] = u['username']
            session['role'] = u['role']

            if u['role'] == 'admin':
                session['name'] = "Admin"
                return redirect('/admin/dashboard')
            
            student = get_student(u['student_id'])
            if student:
                if student.get("status") != "approved":
                    flash("Your registration is pending admin approval.")
                    return redirect('/login')
                session.update({
                    'student_id': student['student_id'],
                    'name': student['name'],
                    'class': student['class'],
                    'school': student['school']
                })
                return redirect('/student/dashboard')
            flash("Student record not found.")
            return redirect('/login')
        flash("Invalid username or password.")
        return redirect('/login')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

#--------------signup-------------------#
otp_store = {}
def send_otp(email, otp):
    from_addr = os.environ.get('EMAIL_SENDER_ADDRESS')
    password = os.environ.get('EMAIL_SENDER_PASSWORD')
    to_addr = email

    subject = "Your OTP for Gajanan Classes"
    body = f"Your OTP is: {otp}\n\nDo not share this with anyone.\n\nRegards,\nGajanan Classes"

    message = f"Subject: {subject}\n\n{body}"

    try:
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(from_addr, password)
            server.sendmail(from_addr, to_addr, message)
        print(f"OTP sent to {email}")
    except Exception as e:
        print("Failed to send OTP:", e)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        contact = request.form['contact']
        name = request.form['name']
        student_class = int(request.form['class'])
        school = request.form['school']

        if not contact.isdigit() or len(contact) != 10:
            flash("Phone number must be 10 digits.")
            return redirect('/signup')
        
        existing_user = users_col.find_one({"$or": [{"email": email}, {"contact": contact}]})
        if existing_user:
            flash("An account with this email or phone already exists.")
            return redirect('/signup')

        if users_col.find_one({"username": username}):
            flash("Username already exists.")
            return redirect('/signup')
        
        if not is_strong_password(password):
            flash("Password must be at least 8 characters and include uppercase, lowercase, number, and special character.")
            return redirect('/signup')


        otp = str(random.randint(100000, 999999))
        otp_store[email] = {
            "otp": otp,
            "data": {
                "username": username,
                "password": password,
                "email": email,
                "contact": contact,
                "name": name,
                "class": student_class,
                "school": school
            }
        }

        send_otp(email, otp)
        session['pending_email'] = email
        flash("OTP sent to your email.")
        return redirect('/verify-otp')
    return render_template('signup.html',
                           schools=metadata.get("schools", []),
                           classes=metadata.get("classes", []))

@app.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    email = session.get('pending_email')
    if not email or email not in otp_store:
        flash("No pending verification.")
        return redirect('/signup')

    if request.method == 'POST':
        otp_input = request.form['otp']
        otp_record = otp_store[email]
        if otp_input == otp_record['otp']:
            data = otp_record['data']
            student_id = str(students_col.count_documents({}) + 1)
            hashed = bcrypt.hashpw(data['password'].encode(), bcrypt.gensalt())
            today, *_ =get_ist_today_range()
            students_col.insert_one({
                "student_id": student_id,
                "name": data['name'],
                "class": data['class'],
                "school": data['school'],
                "contact": data['contact'],
                "status": "pending",  # or "approved" once admin verifies
                "category": "live"
            })

            users_col.insert_one({
                "username": data['username'],
                "password": hashed,
                "email": data['email'],
                "role": "student",
                "student_id": student_id,
                "created_at": today,
                "last_login": None
            })

            otp_store.pop(email)
            session.pop('pending_email', None)
            flash("Signup successful. Please login.")
            return redirect('/login')
        else:
            flash("Incorrect OTP.")
    return render_template('verify_otp.html')

#----------------reset pass------------------#
reset_otp_store = {}

@app.route('/reset-password', methods=['GET', 'POST'])
def reset_password_request():
    if request.method == 'POST':
        email = request.form['email']
        user = users_col.find_one({"email": email})
        if not user:
            flash("Email not registered.")
            return redirect('/reset-password')

        otp = str(random.randint(100000, 999999))
        reset_otp_store[email] = otp
        send_otp(email, otp)
        session['reset_email'] = email
        flash("OTP sent to your email.")
        return redirect('/reset-password/verify')
    return render_template('reset_password.html')

@app.route('/reset-password/verify', methods=['GET', 'POST'])
def reset_password_verify():
    email = session.get('reset_email')
    if request.method == 'POST':
        otp_input = request.form['otp']
        if reset_otp_store.get(email) == otp_input:
            return redirect('/reset-password/new')
        else:
            flash("Invalid OTP.")
    return render_template('verify_otp.html')

@app.route('/reset-password/new', methods=['GET', 'POST'])
def reset_password_new():
    email = session.get('reset_email')
    if request.method == 'POST':
        new_password = request.form['password']
        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
        users_col.update_one({"email": email}, {"$set": {"password": hashed}})
        flash("Password updated. Login again.")
        return redirect('/login')
    return render_template('set_new_password.html')


#---------------Admin Views-----------------#
@app.route('/admin/dashboard')
@login_required('admin')
def admin_dashboard():
    test_exists = tests_col.count_documents({}) > 0
    return render_template('admin/dashboard.html', test_exists=test_exists)

@app.route('/admin/pending-students')
@login_required('admin')
def pending_students():
    pending = list(students_col.find({"status": "pending"}))
    return render_template('admin/pending_students.html', students=pending)

@app.route('/admin/approve-student/<student_id>', methods=["POST"])
@login_required('admin')
def approve_student(student_id):
    students_col.update_one({"student_id": student_id}, {"$set": {"status": "approved"}})
    flash("Student approved.")
    return redirect('/admin/pending-students')


@app.route('/admin/reject-student/<student_id>', methods=["POST"])
@login_required('admin')
def reject_student(student_id):
    students_col.delete_one({"student_id": student_id})
    users_col.delete_one({"student_id": student_id})
    flash("Student rejected and removed.")
    return redirect('/admin/pending-students')


@app.route('/admin/students')
@login_required('admin')
def view_students():
    students = list(students_col.find({"category":"live"},{"status":"approved"}))
    return render_template('admin/students.html', students=students)

@app.route('/admin/ex-students')
@login_required('admin')
def view_ex_students():
    students = list(students_col.find({"category":"ex"}))
    return render_template('admin/ex_students.html', students=students)

@app.route('/admin/add-schedule', methods=['GET', 'POST'])
@login_required('admin')
def add_schedule():
    if request.method == 'POST':
        date_str= request.form['date']  # format: YYYY-MM-DD
        
        schedules_col.insert_one({
            "class": int(request.form['class']),
            "school": request.form['school'],
            "subject": request.form['subject'],
            "date": datetime.strptime(date_str, '%Y-%m-%d'),
            "schedule_time": request.form['schedule_time']
        })
        return redirect('/schedules')
    return render_template('admin/add_schedule.html',
                           subjects=metadata.get("subjects", []),
                           schools=metadata.get("schools", []),
                           classes=metadata.get("classes", []))

@app.route('/admin/add-test', methods=['GET', 'POST'])
@login_required('admin')
def add_test():
    if request.method == 'POST':
        test_date_str = request.form['date']
        file = request.files.get('question_paper')

        filename = None
        if file and allowed_file(file.filename):
            upload_result = cloudinary.uploader.upload(file, folder="tests", resource_type="auto", type="upload")
            file_url = upload_result['secure_url']
        else:
            flash("Invalid file type. Upload PDF or image only.")
            return redirect('/admin/add-test')

        tests_col.insert_one({
            "class": int(request.form['class']),
            "school": request.form.get('school'),
            "subject": request.form.get('subject'),
            "test_date": datetime.strptime(test_date_str, '%Y-%m-%d'),
            "max_marks": int(request.form['max_marks']),
            "description": request.form.get('description', ''),
            "question_paper": file_url, 
        })
        flash("Test added successfully.")
        return redirect('/tests')
    return render_template('admin/add_test.html', 
                           subjects=metadata.get("subjects", []),
                           schools=metadata.get("schools", []),
                           classes=metadata.get("classes", []))

@app.route('/admin/delete-student/<id>')
@login_required('admin')
def delete_student(id):
    students_col.update_one({"_id": ObjectId(id)}, {"$set": {"category": "ex"}})
    users_col.delete_one({"_id": ObjectId(id)})
    return redirect('/admin/students')

@app.route('/admin/delete-test/<id>')
@login_required('admin')
def delete_test(id):
    tests_col.delete_one({"_id": ObjectId(id)})
    return redirect('/tests')

@app.route('/admin/delete-schedule/<id>')
@login_required('admin')
def delete_schedule(id):
    schedules_col.delete_one({"_id": ObjectId(id)})
    return redirect('/schedules')

@app.route('/admin/submitted-answers')
@login_required('admin')
def view_submitted_answers():
    test_id = request.args.get('test_id')
    student_id = request.args.get('student_id')

    query = {}
    if test_id:
        query['test_id'] = ObjectId(test_id)
    if student_id:
        query['student_id'] = student_id

    answers = list(answers_col.find(query).sort("upload_time", -1))

    if not answers:
        flash("No submitted answers found.")
        return render_template('admin/submitted_answers.html', answers=[], students={}, tests={})

    # Get unique student_ids and test_ids from the results
    student_ids = list(set(a['student_id'] for a in answers))
    test_ids = list(set(a['test_id'] for a in answers))

    # Fetch related students and tests
    students = {
        s['student_id']: s
        for s in students_col.find({"student_id": {"$in": student_ids}})
    }

    tests = {
        str(t['_id']): t
        for t in tests_col.find({"_id": {"$in": test_ids}})
    }

    return render_template('admin/submitted_answers.html', answers=answers, students=students, tests=tests)

@app.route('/admin/update-marks', methods=['POST'])
@login_required('admin')
def update_marks():
    data = request.get_json()
    answer_id = data.get('answer_id')
    marks = int(data.get('marks'))

    answers_col.update_one(
        {"_id": ObjectId(answer_id)},
        {"$set": {"marks_obtained": marks, "status": "graded"}}
    )
    return '', 204

@app.route('/admin/manage-metadata', methods=['GET', 'POST'])
@login_required('admin')
def manage_metadata():
    global metadata
    metadata=db.metadata.find_one({"_id": "config"})
    if request.method == 'POST':
        field = request.form['field']
        value = request.form['value'].strip()

        if value:
            if field in ['subjects', 'schools']:
                db.metadata.update_one({"_id": "config"}, {"$addToSet": {field: value}})
            elif field == 'classes':
                try:
                    value = int(value)
                    db.metadata.update_one({"_id": "config"}, {"$addToSet": {field: value}})
                except ValueError:
                    flash("Class must be a number.")
                    return redirect('/admin/manage-metadata')

        return redirect('/admin/manage-metadata')

    return render_template('admin/manage_metadata.html', metadata=metadata)

@app.route('/admin/delete-metadata/<field>/<value>')
@login_required('admin')
def delete_metadata(field, value):
    if field == 'classes':
        try:
            value = int(value)
        except ValueError:
            flash("Invalid class value.")
            return redirect('/admin/manage-metadata')
    db.metadata.update_one({"_id": "config"}, {"$pull": {field: value}})
    return redirect('/admin/manage-metadata')


#-----------------Student Views---------------#
@app.route('/student/dashboard')
@login_required('student')
def student_dashboard():
    _, start, end=get_ist_today_range()
    
    # Fetch all tests scheduled for today for this student
    tests_today = list(tests_col.find({
        "class": session.get('class'),
        "school": session.get('school'),
        "test_date": {"$gte": start, "$lte": end}
    }))

    # Get all uploaded answers by the student
    uploaded_answers = {
        str(a['test_id']): a
        for a in answers_col.find({
            "student_id": session.get('student_id')
        })
    }

    # Check if any test today does not have an uploaded answer
    pending_upload = any(
        str(t['_id']) not in uploaded_answers
        for t in tests_today
    )

    return render_template('student/dashboard.html', pending_upload=pending_upload)

@app.route('/student/profile')
@login_required('student')
def student_profile():
    student_id = session.get('student_id')
    student = students_col.find_one({"student_id": student_id})
    user = users_col.find_one({"student_id": student_id})
    return render_template('student/profile.html', student=student, user=user)

@app.route('/student/upload-answer/<test_id>', methods=['POST'])
@login_required('student')
def student_upload_answer(test_id):
    student_id = session.get('student_id')
    _, start, end=get_ist_today_range()

    test = tests_col.find_one({
        "_id": ObjectId(test_id),
        "class": session.get('class'),
        "school": session.get('school'),
        "test_date": {"$gte": start, "$lte": end}
    })

    if not test:
        flash("This test is either not assigned today or not found.")
        return redirect('/tests')

    if answers_col.find_one({"student_id": student_id, "test_id": ObjectId(test_id)}):
        flash("You have already uploaded the answer for this test.")
        return redirect('/tests')

    file = request.files.get('pdf_file')
    if not file or not allowed_file(file.filename) or not file.filename.lower().endswith('.pdf'):
        flash("Invalid file. Only PDF allowed.")
        return redirect('/tests')

    try:
        upload_result = cloudinary.uploader.upload(
            file,
            folder="answers",
            resource_type="auto",
            type="upload"
        )
        file_url = upload_result['secure_url']
    except Exception:
        flash("File upload failed.")
        return redirect('/tests')

    # Save normalized answer record
    today, *_=get_ist_today_range()
    answers_col.insert_one({
        "student_id": student_id,
        "test_id": ObjectId(test_id),
        "file_url": file_url,
        "upload_time": today,
        "status": "pending",
    })

    flash("Answer uploaded successfully.")
    return redirect('/tests')

#-------------common temp-------------#
@app.route('/schedules')
@login_required_any('admin','student')
def view_schedules():
    try:
        _, start, _ =get_ist_today_range()
        if session.get('role') == 'admin':
            schedules = list(schedules_col.find().sort("date", -1))
            can_add = True
        else:
            schedules = list(schedules_col.find({
                "class": session.get('class'),
                "school": session.get('school'),
                "date": {"$gte": start}
            }))
            can_add = False
        return render_template('schedules.html', schedules=schedules, can_add=can_add)
    except Exception as e:
        print("Error in /schedules:", e)
        return "Internal Server Error", 500

@app.route('/tests')
@login_required_any('admin','student')
def view_tests():
    try:
        role = session.get('role')
        
        if role == 'admin':
            tests = list(tests_col.find().sort("test_date",-1))
            can_add = True
            return render_template('tests.html', tests=tests, can_add=can_add)

        elif role == 'student':
            _, start, end=get_ist_today_range()

            tests = list(tests_col.find({
                "class": session.get('class'),
                "school": session.get('school'),
                "test_date": {"$gte": start, "$lte": end}
            }))

            uploaded = {
                str(a['test_id']): a
                for a in answers_col.find({
                    "student_id": session.get('student_id')
                })
            }
            can_add = False
            return render_template('tests.html', tests=tests, uploaded_answers=uploaded, can_add=can_add)
    except Exception as e:
        print("Error in /tests:", e)
        return "Internal Server Error", 500



if __name__ == '__main__':
    app.run(debug=True)