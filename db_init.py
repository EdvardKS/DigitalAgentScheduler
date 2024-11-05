from flask import Flask
from models import db, Appointment
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

db.init_app(app)

with app.app_context():
    # Drop all tables
    db.drop_all()
    # Create all tables with new schema
    db.create_all()
    print("Database tables recreated successfully!")
