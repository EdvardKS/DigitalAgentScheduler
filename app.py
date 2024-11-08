import os
from flask import Flask, render_template, request, jsonify, session, make_response
from datetime import datetime, time, timedelta
from chatbot import generate_response
from functools import wraps
from flask_mail import Mail
from email_utils import mail, send_appointment_confirmation, schedule_reminder_email, send_contact_form_notification
from models import db, Appointment, ContactSubmission
from sqlalchemy import func
import logging
import re
from dotenv import load_dotenv
from werkzeug.security import generate_password_hash, check_password_hash

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

# Enhanced configuration
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY"),
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_recycle": 300,
        "pool_pre_ping": True,
    },
    PERMANENT_SESSION_LIFETIME=timedelta(days=7),
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)

# Mail configuration
app.config.update(
    MAIL_SERVER=os.getenv('MAIL_SERVER'),
    MAIL_PORT=int(os.getenv('MAIL_PORT', 465)),
    MAIL_USE_TLS=os.getenv('MAIL_USE_TLS', 'False').lower() == 'true',
    MAIL_USE_SSL=os.getenv('MAIL_USE_SSL', 'True').lower() == 'true',
    MAIL_USERNAME=os.getenv('MAIL_USERNAME'),
    MAIL_PASSWORD=os.getenv('MAIL_PASSWORD'),
    BASE_URL=os.getenv('BASE_URL', 'http://localhost:5000')
)

# Initialize extensions
db.init_app(app)
mail.init_app(app)

def check_rate_limit(ip):
    """Check if the request should be rate limited"""
    now = datetime.now()
    request_counts[ip] = [t for t in request_counts[ip] if now - t < timedelta(seconds=RATE_WINDOW)]
    request_counts[ip].append(now)
    return len(request_counts[ip]) <= RATE_LIMIT

def validate_password(password):
    """Validate password complexity"""
    if len(password) < 8:
        return False, "La contraseña debe tener al menos 8 caracteres"
    
    if not re.search(r"[A-Z]", password):
        return False, "La contraseña debe contener al menos una letra mayúscula"
        
    if not re.search(r"[a-z]", password):
        return False, "La contraseña debe contener al menos una letra minúscula"
        
    if not re.search(r"\d", password):
        return False, "La contraseña debe contener al menos un número"
        
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):
        return False, "La contraseña debe contener al menos un carácter especial"
        
    return True, None

# Enhanced PIN protection decorator
def require_pin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('pin_verified'):
            logger.warning("Unauthorized access attempt - Authentication required")
            return jsonify({"error": "Unauthorized", "code": "AUTH_REQUIRED"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Session check endpoint
@app.route('/api/check-session')
def check_session():
    return jsonify({"authenticated": bool(session.get('pin_verified'))})

# Enhanced authentication endpoint
@app.route('/api/verify-pin', methods=['POST'])
def verify_pin():
    try:
        data = request.get_json()
        password = data.get('pin')  # Keeping pin field for backward compatibility
        remember_me = data.get('remember_me', False)
        stored_password = os.getenv('CHATBOT_PIN')
        
        if not password or not stored_password:
            logger.warning("Missing password in verification attempt")
            return jsonify({"success": False, "error": "Contraseña requerida"}), 400

        # Validate password complexity for new passwords
        if password != stored_password and len(password) > 4:  # Only validate if it's a new complex password
            is_valid, error_message = validate_password(password)
            if not is_valid:
                logger.warning(f"Invalid password format: {error_message}")
                return jsonify({"success": False, "error": error_message}), 400

        # If it's the old PIN format, do direct comparison
        if len(stored_password) == 4 and password == stored_password:
            logger.info("Legacy PIN verification successful")
            session.permanent = remember_me
            session['pin_verified'] = True
            session['pin_timestamp'] = datetime.now().timestamp()
            return jsonify({"success": True})

        # For complex passwords, use secure comparison
        if check_password_hash(stored_password, password):
            logger.info("Password verification successful")
            session.permanent = remember_me
            session['pin_verified'] = True
            session['pin_timestamp'] = datetime.now().timestamp()
            return jsonify({"success": True})
            
        logger.warning("Invalid password attempt")
        return jsonify({"success": False, "error": "Contraseña inválida"}), 401
        
    except Exception as e:
        logger.error(f"Error in password verification: {str(e)}")
        return jsonify({"success": False, "error": "Error de servidor"}), 500

# Logout endpoint
@app.route('/api/logout', methods=['POST'])
def logout():
    try:
        session.clear()
        logger.info("User logged out successfully")
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}")
        return jsonify({"success": False, "error": "Error during logout"}), 500

# Main routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/citas')
def appointment_management():
    return render_template('appointment_management.html')

# API endpoints
@app.route('/api/contact-submissions', methods=['GET'])
@require_pin
def get_contact_submissions():
    try:
        logger.info("Fetching contact submissions from database")
        submissions = ContactSubmission.query.order_by(ContactSubmission.created_at.desc()).all()
        logger.info(f"Found {len(submissions)} contact submissions")
        
        submissions_list = []
        for submission in submissions:
            submission_data = {
                'id': submission.id,
                'nombre': submission.nombre,
                'email': submission.email,
                'telefono': submission.telefono,
                'dudas': submission.dudas,
                'created_at': submission.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            submissions_list.append(submission_data)
            logger.debug(f"Processed submission: {submission_data}")
        
        return jsonify({"submissions": submissions_list})
    except Exception as e:
        logger.error(f"Error fetching contact submissions: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching contact submissions", "details": str(e)}), 500

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

@app.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
@require_pin
def delete_appointment(appointment_id):
    try:
        appointment = Appointment.query.get(appointment_id)
        if not appointment:
            return jsonify({"error": "Appointment not found"}), 404
        
        db.session.delete(appointment)
        db.session.commit()
        logger.info(f"Appointment {appointment_id} deleted successfully")
        
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
        
        # Update appointment fields
        appointment.name = data.get('name', appointment.name)
        appointment.email = data.get('email', appointment.email)
        appointment.phone = data.get('phone')
        appointment.date = datetime.strptime(data.get('date'), '%Y-%m-%d').date()
        appointment.time = data.get('time', appointment.time)
        appointment.service = data.get('service', appointment.service)
        appointment.status = data.get('status', 'Pendiente')
        
        db.session.commit()
        logger.info(f"Appointment {appointment_id} updated successfully")
        
        return jsonify({
            "message": "Appointment updated successfully",
            "appointment": {
                'id': appointment.id,
                'name': appointment.name,
                'email': appointment.email,
                'phone': appointment.phone,
                'date': appointment.date.strftime('%Y-%m-%d'),
                'time': appointment.time,
                'service': appointment.service,
                'status': appointment.status,
                'created_at': appointment.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        })
    except Exception as e:
        logger.error(f"Error updating appointment: {str(e)}")
        return jsonify({"error": "Error updating appointment"}), 500

@app.route('/api/contact', methods=['POST'])
def handle_contact_form():
    try:
        data = request.get_json()
        
        # Validate form data
        validation_errors = validate_contact_form(data)
        if validation_errors:
            return jsonify({
                "error": "Errores de validación",
                "validation_errors": validation_errors
            }), 400
        
        try:
            # Create contact submission record
            submission = ContactSubmission(
                nombre=data['nombre'],
                email=data['email'],
                telefono=data['telefono'],
                dudas=data['dudas']
            )
            db.session.add(submission)
            db.session.commit()
            
            # Send email notifications
            send_contact_form_notification(data)
            
            return jsonify({
                "message": "Formulario enviado exitosamente",
                "detail": "Hemos recibido tu consulta y nos pondremos en contacto contigo pronto."
            }), 200
            
        except Exception as e:
            logger.error(f"Error processing contact form: {str(e)}")
            db.session.rollback()
            return jsonify({
                "error": "Error al procesar el formulario",
                "detail": "Hubo un problema al enviar tu consulta. Por favor, inténtalo de nuevo más tarde."
            }), 500
            
    except Exception as e:
        logger.error(f"Error handling contact form submission: {str(e)}")
        return jsonify({
            "error": "Error del servidor",
            "detail": "Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo más tarde."
        }), 500

@app.route('/api/chatbot', methods=['POST'])
def chatbot_response():
    client_ip = request.remote_addr
    if not check_rate_limit(client_ip):
        return jsonify({
            "error": "Rate limit exceeded",
            "retry_after": RATE_WINDOW
        }), 429

    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        message = data.get('message', '').strip()
        if not message:
            return jsonify({"error": "Empty message"}), 400

        conversation_history = data.get('conversation_history', [])
        response = generate_response(message, conversation_history)
        return jsonify({"response": response})

    except Exception as e:
        logger.error(f"Error in chatbot response: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500

def validate_contact_form(data):
    """Validate contact form data"""
    errors = {}
    
    # Required fields
    required_fields = {
        'nombre': 'Nombre es requerido',
        'email': 'Email es requerido',
        'telefono': 'Teléfono es requerido',
        'dudas': 'Por favor, describe tus dudas'
    }
    
    for field, message in required_fields.items():
        if not data.get(field):
            errors[field] = message
    
    # Email validation
    if data.get('email') and not re.match(r"[^@]+@[^@]+\.[^@]+", data['email']):
        errors['email'] = 'Email inválido'
    
    # Phone validation (Spanish format)
    if data.get('telefono') and not re.match(r"^(?:\+34|0034|34)?[6789]\d{8}$", data['telefono']):
        errors['telefono'] = 'Número de teléfono inválido'
    
    return errors

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}", exc_info=True)
    
    app.run(host='0.0.0.0', port=5000)
