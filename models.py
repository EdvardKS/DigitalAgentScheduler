from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import os

db = SQLAlchemy()

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.String(10), nullable=False)
    service = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
