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
import time as time_module

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

# Database configuration with enhanced error handling and retry logic
def init_db_with_retry(max_retries=5, retry_delay=2):
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("DATABASE_URL not found in environment variables")
        raise ValueError("DATABASE_URL is required")

    logger.info("Configuring database connection...")
    
    for attempt in range(max_retries):
        try:
            app.config["SQLALCHEMY_DATABASE_URI"] = db_url
            app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
                "pool_recycle": 300,
                "pool_pre_ping": True,
                "connect_args": {
                    "connect_timeout": 10,
                    "keepalives": 1,
                    "keepalives_idle": 30,
                    "keepalives_interval": 10,
                    "keepalives_count": 5
                }
            }
            app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
            
            # Initialize db
            db.init_app(app)
            
            # Test connection
            with app.app_context():
                db.engine.connect()
                logger.info("Database connection successful")
                return True
                
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database connection attempt {attempt + 1} failed: {str(e)}")
                time_module.sleep(retry_delay)
            else:
                logger.error(f"All database connection attempts failed: {str(e)}", exc_info=True)
                raise

# Mail configuration
mail_config = {
    'MAIL_SERVER': os.getenv('MAIL_SERVER'),
    'MAIL_PORT': int(os.getenv('MAIL_PORT', 465)),
    'MAIL_USE_TLS': os.getenv('MAIL_USE_TLS', 'False').lower() == 'true',
    'MAIL_USE_SSL': os.getenv('MAIL_USE_SSL', 'True').lower() == 'true',
    'MAIL_USERNAME': os.getenv('MAIL_USERNAME'),
    'MAIL_PASSWORD': os.getenv('MAIL_PASSWORD')
}

# Verify mail configuration
for key, value in mail_config.items():
    if value is None:
        logger.error(f"Mail configuration missing: {key}")
        raise ValueError(f"Mail configuration missing: {key}")
    app.config[key] = value

app.config['BASE_URL'] = os.getenv('BASE_URL', 'http://localhost:5000')

# Initialize extensions with error handling
try:
    logger.info("Initializing database...")
    init_db_with_retry()
    
    logger.info("Initializing mail service...")
    mail.init_app(app)
except Exception as e:
    logger.error(f"Error initializing extensions: {str(e)}", exc_info=True)
    raise

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
        
        logger.info(f"Successfully fetched {len(appointments_list)} appointments")
        return jsonify({"appointments": appointments_list})
    except Exception as e:
        logger.error(f"Error fetching appointments: {str(e)}", exc_info=True)
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
        logger.info(f"Successfully deleted appointment {appointment_id}")
        
        return jsonify({"message": "Appointment deleted successfully"})
    except Exception as e:
        logger.error(f"Error deleting appointment {appointment_id}: {str(e)}", exc_info=True)
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
        if not all(key in data for key in ['name', 'email', 'date', 'time', 'service']):
            return jsonify({"error": "Missing required fields"}), 400
            
        # Update appointment
        appointment.name = data['name']
        appointment.email = data['email']
        appointment.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
        appointment.time = data['time']
        appointment.service = data['service']
        
        db.session.commit()
        logger.info(f"Successfully updated appointment {appointment_id}")
        
        return jsonify({
            "message": "Appointment updated successfully",
            "appointment": {
                'id': appointment.id,
                'name': appointment.name,
                'email': appointment.email,
                'date': appointment.date.strftime('%Y-%m-%d'),
                'time': appointment.time,
                'service': appointment.service
            }
        })
    except Exception as e:
        logger.error(f"Error updating appointment {appointment_id}: {str(e)}", exc_info=True)
        return jsonify({"error": "Error updating appointment"}), 500

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
            logger.info("Creating database tables...")
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {str(e)}", exc_info=True)
            raise
    
    app.run(host='0.0.0.0', port=5000)
