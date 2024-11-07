import os
from flask import Flask, render_template, request, jsonify, session
from datetime import datetime, time, timedelta
from chatbot import generate_response
from functools import wraps
from flask_mail import Mail
from email_utils import mail, send_appointment_confirmation, schedule_reminder_email, send_contact_form_notification
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

# Decorator for PIN protection
def require_pin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('pin_verified'):
            logger.warning("PIN verification required but not found in session")
            return jsonify({"error": "PIN verification required"}), 401
        return f(*args, **kwargs)
    return decorated_function

# Validation functions
def validar_nombre(nombre):
    return bool(re.match("^[A-Za-zÀ-ÿ\s]{2,100}$", nombre))

def validar_correo(correo):
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", correo))

def validate_contact_form(data):
    """Validate contact form data"""
    errors = {}
    
    # Required fields
    required_fields = {
        'nombre': 'Nombre es requerido',
        'email': 'Email es requerido',
        'telefono': 'Teléfono es requerido',
        'direccion': 'Dirección es requerida',
        'codigoPostal': 'Código Postal es requerido',
        'ciudad': 'Ciudad es requerida',
        'provincia': 'Provincia es requerida',
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
    
    # Postal code validation (Spanish format)
    if data.get('codigoPostal') and not re.match(r"^\d{5}$", data['codigoPostal']):
        errors['codigoPostal'] = 'Código postal inválido'
    
    return errors

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
            # Send email notifications
            send_contact_form_notification(data)
            
            # Create appointment record if needed
            if data.get('requiere_cita', False):
                appointment = Appointment(
                    name=data['nombre'],
                    email=data['email'],
                    phone=data['telefono'],
                    date=datetime.now().date() + timedelta(days=1),  # Schedule for tomorrow by default
                    time="10:30",  # Default time slot
                    service="Consulta General",
                    status="Pendiente"
                )
                db.session.add(appointment)
                db.session.commit()
                logger.info(f"Created appointment from contact form: {appointment.id}")
            
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

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}", exc_info=True)
    
    app.run(host='0.0.0.0', port=5000)
