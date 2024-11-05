from flask import Flask
from models import db, Appointment
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

db.init_app(app)

with app.app_context():
    try:
        # Check if we have any appointments
        count = Appointment.query.count()
        print(f"Current appointment count: {count}")
        
        if count == 0:
            # Create a test appointment
            test_appointment = Appointment(
                name="Test User",
                email="test@example.com",
                phone="673660910",
                date=datetime.now().date(),
                time="10:30",
                service="Inteligencia Artificial (hasta 6.000€)",
                status="Pendiente"
            )
            db.session.add(test_appointment)
            db.session.commit()
            print("Test appointment created successfully!")
        
        # Verify the appointment was created
        appointments = Appointment.query.all()
        for apt in appointments:
            print(f"Found appointment: ID={apt.id}, Name={apt.name}, Date={apt.date}")
            
    except Exception as e:
        print(f"Error: {str(e)}")
