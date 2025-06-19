from flask import Flask, render_template, request, redirect, session, flash
from pymongo import MongoClient
from werkzeug.utils import secure_filename
import os
import datetime

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY')


app.config['UPLOAD_FOLDER'] = 'static/uploads'
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])


# MongoDB connection
MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['sanskrit_tutor']
users_col = db['users']
students_col = db['students']
tests_col = db['tests']
schedules_col = db['schedules']

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
        if u and u['password'] == password:
            session['username'] = u['username']
            session['role'] = u['role']
            if u['role'] == 'admin':
                return redirect('/admin/dashboard')
            else:
                session['student_id'] = u['student_id']
                return redirect('/student/dashboard')
        
        flash("Invalid username or password.")
        return redirect('/login')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')



@app.route('/')
def home():
    if 'role' in session:
        if session['role'] == 'admin':
            return redirect('/admin/dashboard')
        elif session['role'] == 'student':
            return redirect('/student/dashboard')
    return redirect('/login')

@app.route('/admin/dashboard')
def admin_dashboard():
    if session.get('role') != 'admin':
        return redirect('/login')
    test_exists = tests_col.count_documents({}) > 0
    return render_template('admin/dashboard.html', test_exists=test_exists)


@app.route('/student/dashboard')
def student_dashboard():
    if session.get('role') != 'student':
        return redirect('/login')

    student_id = session.get('student_id')
    test_exists = tests_col.count_documents({"type": "assigned"}) > 0

    return render_template('student/dashboard.html', test_exists=test_exists)


@app.route('/admin/students')
def view_students():
    if session.get('role') != 'admin':
        return redirect('/login')
    students = list(students_col.find())
    return render_template('admin/students.html', students=students)

@app.route('/admin/tests')
def admin_view_tests():
    if session.get('role') != 'admin':
        return redirect('/login')
    tests = list(tests_col.find())
    return render_template('admin/tests.html', tests=tests)


@app.route('/admin/schedules')
def view_schedules():
    if session.get('role') != 'admin':
        return redirect('/login')
    schedules = list(schedules_col.find())
    return render_template('admin/schedules.html', schedules=schedules)

@app.route('/admin/view-marks/<student_id>')
def view_marks(student_id):
    if session.get('role') != 'admin':
        return redirect('/login')
    student = students_col.find_one({"student_id": student_id})
    tests = list(tests_col.find({"student_id": student_id}))
    return render_template('admin/view_marks.html', student=student, tests=tests)



@app.route('/admin/add-student', methods=['GET', 'POST'])
def add_student():
    if session.get('role') != 'admin':
        return redirect('/login')
    if request.method == 'POST':
        student_data = {
            "student_id": request.form['student_id'],
            "name": request.form['name'],
            "class": int(request.form['class']),
            "school": request.form['school'],
            "contact": request.form['contact']
        }
        existing = students_col.find_one({"student_id": request.form['student_id']})
        if existing:
            flash("Student ID already exists.")
            return redirect('/admin/add-student')
        students_col.insert_one(student_data)
        return redirect('/admin/students')  # redirect after adding

    return render_template('admin/add_student.html')

@app.route('/admin/add-schedule', methods=['GET', 'POST'])
def add_schedule():
    if session.get('role') != 'admin':
        return redirect('/login')
    if request.method == 'POST':
        schedule_data = {
            "class": int(request.form['class']),
            "school": request.form['school'],
            "day": request.form['day'],
            "time": request.form['time']
        }
        schedules_col.insert_one(schedule_data)
        return redirect('/admin/schedules')
    
    return render_template('admin/add_schedule.html')

from bson.objectid import ObjectId

@app.route('/admin/delete-student/<id>')
def delete_student(id):
    if session.get('role') != 'admin':
        return redirect('/login')
    students_col.delete_one({"_id": ObjectId(id)})
    return redirect('/admin/students')

@app.route('/admin/delete-test/<id>')
def delete_test(id):
    if session.get('role') != 'admin':
        return redirect('/login')
    tests_col.delete_one({"_id": ObjectId(id)})
    return redirect('/admin/tests')

@app.route('/admin/delete-schedule/<id>')
def delete_schedule(id):
    if session.get('role') != 'admin':
        return redirect('/login')
    schedules_col.delete_one({"_id": ObjectId(id)})
    return redirect('/admin/schedules')

@app.route('/admin/add-test', methods=['GET', 'POST'])
def add_test():
    if session.get('role') != 'admin':
        return redirect('/login')
    if request.method == 'POST':
        file = request.files.get('question_paper')
        filename = None

        if file and allowed_file(file.filename):
            filename = secure_filename(f"{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))


        test_data = {
            "subject": request.form['subject'],
            "test_date": request.form['test_date'],
            "class": int(request.form['class']),
            "question_paper": filename,  # saved name of the uploaded file
            "type": "assigned"  # this marks it as created by tutor
        }

        tests_col.insert_one(test_data)
        return redirect('/admin/tests')

    return render_template('admin/add_test.html')


@app.route('/admin/answers/<student_id>')
def admin_view_answers(student_id):
    if session.get('role') != 'admin':
        return redirect('/login')
    answers = list(db['answers'].find({"student_id": student_id}))
    student = students_col.find_one({"student_id": student_id})
    return render_template('admin/view_answers.html', answers=answers, student=student)



@app.route('/student/upload-answer', methods=['GET', 'POST'])
def student_upload_answer():
    if session.get('role') != 'student':
        return redirect('/login')

    student_id = session.get('student_id')

    
    active_test = tests_col.find_one({"type": "assigned"})
    if not active_test:
        flash("No active test. Upload disabled.")
        return redirect('/student/dashboard')

    if request.method == 'POST':
        file = request.files.get('pdf_file')

        if file and allowed_file(file.filename) and file.filename.lower().endswith('.pdf'):
            filename = secure_filename(f"{student_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            try:
                file.save(filepath)
            except Exception as e:
                flash("File upload failed.")
                return redirect('/student/upload-answer')


            db['answers'].insert_one({
                "student_id": student_id,
                "filename": filename,
                "upload_time": datetime.datetime.utcnow()
            })

            flash("Answer PDF uploaded successfully.")
            return redirect('/student/upload-answer')
        else:
            flash("Invalid file. Only PDF format is accepted.")
            return redirect('/student/upload-answer')

    return render_template('student/upload_answer.html')



@app.route('/student/schedules')
def student_view_schedules():
    if session.get('role') != 'student':
        return redirect('/login')
    schedules = list(schedules_col.find())
    return render_template('student/schedules.html', schedules=schedules)

@app.route('/student/tests')
def student_view_tests():
    if session.get('role') != 'student':
        return redirect('/login')
    student = students_col.find_one({"student_id": session['student_id']})
    tests = list(tests_col.find({"class": student['class']}))
    return render_template('student/tests.html', tests=tests)



if __name__ == '__main__':
    app.run(debug=True)
