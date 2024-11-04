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
        return jsonify({"success": True})
    return jsonify({"success": False})

@app.route('/api/appointments', methods=['GET'])
@require_pin
def get_appointments():
    try:
        appointments = Appointment.query.order_by(Appointment.date.desc(), Appointment.time.desc()).all()
        
        appointments_list = []
        for appointment in appointments:
            appointments_list.append({
                'id': appointment.id,
                'name': appointment.name,
                'email': appointment.email,
                'date': appointment.date.strftime('%Y-%m-%d'),
                'time': appointment.time,
                'service': appointment.service,
                'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            })
        
        return jsonify({"appointments": appointments_list})
    except Exception as e:
        logger.error(f"Error fetching appointments: {str(e)}")
        return jsonify({"error": "Error fetching appointments"}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
@require_pin
def delete_appointment(appointment_id):
    try:
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return jsonify({"error": "Appointment not found"}), 404
        
        db.session.delete(appointment)
        db.session.commit()
        
        return jsonify({"message": "Appointment deleted successfully"})
    except Exception as e:
        logger.error(f"Error deleting appointment: {str(e)}")
        return jsonify({"error": "Error deleting appointment"}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['PUT'])
@require_pin
def update_appointment(appointment_id):
    try:
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return jsonify({"error": "Appointment not found"}), 404
        
        data = request.get_json()
        
        # Validate input data
        if not validar_nombre(data.get('name', '')):
            return jsonify({"error": "Invalid name format"}), 400
        if not validar_correo(data.get('email', '')):
            return jsonify({"error": "Invalid email format"}), 400
            
        # Validate date and time
        try:
            new_date = datetime.strptime(data.get('date', ''), '%Y-%m-%d').date()
            if new_date < datetime.now().date():
                return jsonify({"error": "Cannot schedule appointments in the past"}), 400
            
            dias_disponibles, horas_disponibles = obtener_disponibilidad()
            if data.get('date') not in dias_disponibles:
                return jsonify({"error": "Selected date is not available"}), 400
            if data.get('time') not in horas_disponibles:
                return jsonify({"error": "Selected time is not available"}), 400
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400
        
        # Update appointment
        appointment.name = data.get('name', appointment.name)
        appointment.email = data.get('email', appointment.email)
        appointment.date = new_date
        appointment.time = data.get('time', appointment.time)
        appointment.service = data.get('service', appointment.service)
        
        db.session.commit()
        
        # Schedule reminder email
        schedule_reminder_email(appointment)
        
        return jsonify({
            "message": "Appointment updated successfully",
            "appointment": {
                'id': appointment.id,
                'name': appointment.name,
                'email': appointment.email,
                'date': appointment.date.strftime('%Y-%m-%d'),
                'time': appointment.time,
                'service': appointment.service,
                'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        logger.error(f"Error updating appointment: {str(e)}")
        return jsonify({"error": "Error updating appointment"}), 500

@app.route('/api/book-appointment', methods=['POST'])
def book_appointment():
    try:
        data = request.get_json()
        
        # Validate input data
        if not validar_nombre(data.get('name', '')):
            return jsonify({"error": "Invalid name format"}), 400
        if not validar_correo(data.get('email', '')):
            return jsonify({"error": "Invalid email format"}), 400
            
        # Validate date and time
        try:
            appointment_date = datetime.strptime(data.get('date', ''), '%Y-%m-%d').date()
            if appointment_date < datetime.now().date():
                return jsonify({"error": "Cannot schedule appointments in the past"}), 400
            
            dias_disponibles, horas_disponibles = obtener_disponibilidad()
            if data.get('date') not in dias_disponibles:
                return jsonify({"error": "Selected date is not available"}), 400
            if data.get('time') not in horas_disponibles:
                return jsonify({"error": "Selected time is not available"}), 400
        except ValueError:
            return jsonify({"error": "Invalid date format"}), 400
        
        # Check for existing appointment at same time
        existing_appointment = Appointment.query.filter_by(
            date=appointment_date,
            time=data.get('time')
        ).first()
        
        if existing_appointment:
            return jsonify({"error": "This time slot is already booked"}), 400
        
        # Create new appointment
        new_appointment = Appointment(
            name=data.get('name'),
            email=data.get('email'),
            date=appointment_date,
            time=data.get('time'),
            service=data.get('service')
        )
        
        db.session.add(new_appointment)
        db.session.commit()
        
        # Send confirmation email and schedule reminder
        send_appointment_confirmation(new_appointment)
        schedule_reminder_email(new_appointment)
        
        return jsonify({
            "message": "Appointment booked successfully",
            "appointment_id": new_appointment.id
        })
        
    except Exception as e:
        logger.error(f"Error booking appointment: {str(e)}")
        return jsonify({"error": "Error booking appointment"}), 500

@app.route('/api/available-slots', methods=['GET'])
def get_available_slots():
    try:
        dias_disponibles, horas_disponibles = obtener_disponibilidad()
        return jsonify({
            "available_dates": dias_disponibles,
            "available_times": horas_disponibles
        })
    except Exception as e:
        logger.error(f"Error fetching available slots: {str(e)}")
        return jsonify({"error": "Error fetching available slots"}), 500

@app.route('/api/chatbot', methods=['POST'])
def chatbot_response():
    """Endpoint for chatbot interactions with enhanced error handling"""
    client_ip = request.remote_addr
    
    try:
        # Rate limiting check
        if not check_rate_limit(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip}")
            return jsonify({
                "error": "Demasiadas solicitudes. Por favor, espera un momento antes de intentar de nuevo.",
                "retry_after": 60
            }), 429

        # Validate request data
        data = request.get_json()
        if not data:
            logger.error("No JSON data in request")
            return jsonify({
                "error": "No se proporcionaron datos en la solicitud.",
                "details": "Request body must contain JSON data"
            }), 400

        message = data.get('message', '').strip()
        if not message:
            logger.warning("Empty message received")
            return jsonify({
                "error": "El mensaje está vacío.",
                "details": "Message field is required"
            }), 400

        # Validate message length
        if len(message) > 500:
            logger.warning(f"Message too long: {len(message)} characters")
            return jsonify({
                "error": "El mensaje es demasiado largo.",
                "details": "Message must not exceed 500 characters"
            }), 400

        conversation_history = data.get('conversation_history', [])
        
        # Log request details
        logger.info(f"Processing chatbot request - IP: {client_ip}, Message length: {len(message)}")
        
        try:
            response = generate_response(message, conversation_history)
            return jsonify({"response": response})
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}", exc_info=True)
            return jsonify({
                "error": "Error al procesar tu mensaje.",
                "details": "Internal server error occurred while processing the message"
            }), 500

    except Exception as e:
        logger.error(f"Unexpected error in chatbot endpoint: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Ha ocurrido un error inesperado.",
            "details": "An unexpected error occurred while processing the request"
        }), 500

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}", exc_info=True)
    
    app.run(host='0.0.0.0', port=5000)
