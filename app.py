import os
from flask import Flask, render_template, request, jsonify, session
from datetime import datetime, time, timedelta
from chatbot import generate_response
from functools import wraps
from flask_mail import Mail
from email_utils import mail, send_appointment_confirmation, schedule_reminder_email
from models import db, Appointment
from sqlalchemy import func
import logging
import re
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up enhanced logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize rate limiting
from datetime import datetime, timedelta
from collections import defaultdict
request_counts = defaultdict(list)
RATE_LIMIT = 30  # requests per minute
RATE_WINDOW = 60  # seconds

app = Flask(__name__)

# Basic configuration
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not app.secret_key:
    logger.error("Flask secret key not found in environment variables")
    raise ValueError("Flask secret key is required")

app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Mail configuration
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT', 465))
app.config['MAIL_USE_TLS'] = os.getenv('MAIL_USE_TLS', 'False').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['BASE_URL'] = os.getenv('BASE_URL', 'http://localhost:5000')

# Initialize extensions
db.init_app(app)
mail.init_app(app)

def check_rate_limit(ip):
    """Check if the request should be rate limited"""
    now = datetime.now()
    request_counts[ip] = [t for t in request_counts[ip] if now - t < timedelta(seconds=RATE_WINDOW)]
    request_counts[ip].append(now)
    return len(request_counts[ip]) <= RATE_LIMIT

# Validation functions from gestion_citas_bot.py
def validar_nombre(nombre):
    return bool(re.match("^[A-Za-zÀ-ÿ\s]{2,100}$", nombre))

def validar_correo(correo):
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", correo))

def obtener_disponibilidad():
    """Get available time slots excluding weekends and past times"""
    dias_disponibles = []
    now = datetime.now()
    
    # Get next 7 available weekdays
    current_date = now.date()
    while len(dias_disponibles) < 7:
        if current_date.weekday() < 5:  # Monday = 0, Friday = 4
            dias_disponibles.append(current_date.strftime("%Y-%m-%d"))
        current_date += timedelta(days=1)
    
    horas_disponibles = ["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00"]
    return dias_disponibles, horas_disponibles

# Decorator for PIN protection
def require_pin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('pin_verified'):
            logger.warning("PIN verification required but not found in session")
            return jsonify({"error": "PIN verification required"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/citas')
def appointment_management():
    return render_template('appointment_management.html')

@app.route('/api/verify-pin', methods=['POST'])
def verify_pin():
    data = request.get_json()
    pin = data.get('pin')
    correct_pin = os.getenv('CHATBOT_PIN')
    
    if pin == correct_pin:
        session['pin_verified'] = True
        logger.info("PIN verification successful")
        return jsonify({"success": True})
    logger.warning("Invalid PIN attempt")
    return jsonify({"success": False})

@app.route('/api/appointments', methods=['GET'])
@require_pin
def get_appointments():
    try:
        logger.info("Fetching appointments from database")
        appointments = Appointment.query.order_by(Appointment.date.desc(), Appointment.time.desc()).all()
        logger.info(f"Found {len(appointments)} appointments")
        
        appointments_list = []
        for appointment in appointments:
            appointment_data = {
                'id': appointment.id,
                'name': appointment.name,
                'email': appointment.email,
                'phone': getattr(appointment, 'phone', None),
                'date': appointment.date.strftime('%Y-%m-%d'),
                'time': appointment.time,
                'service': appointment.service,
                'status': getattr(appointment, 'status', 'Pendiente'),
                'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            appointments_list.append(appointment_data)
            logger.debug(f"Processed appointment: {appointment_data}")
        
        return jsonify({"appointments": appointments_list})
    except Exception as e:
        logger.error(f"Error fetching appointments: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching appointments", "details": str(e)}), 500

[Rest of the file remains the same...]
