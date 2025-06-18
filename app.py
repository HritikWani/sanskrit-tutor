from flask import Flask, request, render_template
from pymongo import MongoClient
from werkzeug.utils import secure_filename
import os

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# MongoDB Connection
MONGO_URI = "mongodb+srv://<username>:<password>@cluster0.mongodb.net/sanskrit_tuition?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
db = client['sanskrit_tuition']
students_col = db['students']
tests_col = db['tests']

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_test():
    file = request.files['file']
    student_id = request.form['student_id']
    subject = request.form['subject']
    test_date = request.form['test_date']
    marks = request.form['marks']

    filename = secure_filename(file.filename)
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    tests_col.insert_one({
        'student_id': student_id,
        'subject': subject,
        'test_date': test_date,
        'marks': marks,
        'pdf_file': filename
    })

    return "Test uploaded successfully."

if __name__ == '__main__':
    app.run(debug=True)
