from flask import Flask, render_template
from pymongo import MongoClient
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# MongoDB Connection
MONGO_URI = os.environ.get("MONGO_URI")

if not MONGO_URI:
    print("Warning: MONGO_URI not set, using localhost for MongoDB.")
    MONGO_URI = "mongodb://localhost:27017"

client = MongoClient(MONGO_URI)
db = client['sanskrit_tuitor']
students_col = db['students']
tests_col = db['tests']
schedules_col = db['schedules']

@app.route('/')
def home():
    return redirect('/admin')

@app.route('/admin')
def admin_page():
    test_exists = tests_col.count_documents({}) > 0
    return render_template('admin.html', test_exists=test_exists)


@app.route('/admin/students')
def view_students():
    students = list(students_col.find())
    return render_template('students.html', students=students)

@app.route('/admin/tests')
def view_tests():
    tests = list(tests_col.find())
    return render_template('tests.html', tests=tests)

@app.route('/admin/schedules')
def view_schedules():
    schedules = list(schedules_col.find())
    return render_template('schedules.html', schedules=schedules)


from flask import request, redirect

@app.route('/admin/add-student', methods=['GET', 'POST'])
def add_student():
    if request.method == 'POST':
        student_data = {
            "student_id": request.form['student_id'],
            "name": request.form['name'],
            "class": int(request.form['class']),
            "school": request.form['school'],
            "contact": request.form['contact']
        }
        students_col.insert_one(student_data)
        return redirect('/admin/students')  # redirect after adding

    return render_template('add_student.html')

@app.route('/admin/add-schedule', methods=['GET', 'POST'])
def add_schedule():
    if request.method == 'POST':
        schedule_data = {
            "class": int(request.form['class']),
            "school": request.form['school'],
            "day": request.form['day'],
            "time": request.form['time']
        }
        schedules_col.insert_one(schedule_data)
        return redirect('/admin/schedules')
    
    return render_template('add_schedule.html')

from bson.objectid import ObjectId

@app.route('/admin/delete-student/<id>')
def delete_student(id):
    students_col.delete_one({"_id": ObjectId(id)})
    return redirect('/admin/students')

@app.route('/admin/delete-test/<id>')
def delete_test(id):
    tests_col.delete_one({"_id": ObjectId(id)})
    return redirect('/admin/tests')

@app.route('/admin/delete-schedule/<id>')
def delete_schedule(id):
    schedules_col.delete_one({"_id": ObjectId(id)})
    return redirect('/admin/schedules')


from flask import request, redirect, flash
import datetime

@app.route('/admin/upload-answer', methods=['GET', 'POST'])
def upload_answer():
    if request.method == 'POST':
        student_id = request.form['student_id']
        file = request.files['pdf_file']

        if file and file.filename.endswith('.pdf'):
            filename = secure_filename(f"{student_id}_{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}.pdf")
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)

            # You can store PDF path and student_id in MongoDB if needed:
            db['answers'].insert_one({
                "student_id": student_id,
                "filename": filename,
                "upload_time": datetime.datetime.utcnow()
            })

            flash("PDF uploaded successfully.")
            return redirect('/admin/upload-answer')
        else:
            flash("Invalid file. Only PDF allowed.")
            return redirect('/admin/upload-answer')

    return render_template('upload_answer.html')



if __name__ == '__main__':
    app.run(debug=True)
