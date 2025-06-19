from pymongo import MongoClient
import os

MONGO_URI = os.environ.get("MONGO_URI")
client = MongoClient(MONGO_URI)
db = client['sanskrit_tutor']

admin_user = {
    "username": "admin",
    "password": "admin123",
    "role": "admin"
}

# Check if admin already exists
if not db.users.find_one({"username": "admin"}):
    db.users.insert_one(admin_user)
    print("Admin user created.")
else:
    print("Admin user already exists.")
