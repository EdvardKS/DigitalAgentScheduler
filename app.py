import os
from flask import Flask, render_template, request, jsonify, session
from datetime import datetime, time, timedelta
from chatbot import generate_response
from functools import wraps
from flask_mail import Mail, Message
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

# Email Configuration
def configure_email():
    """Configure email settings with error handling"""
    required_vars = ['MAIL_USERNAME', 'MAIL_PASSWORD']
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        error_msg = f"Missing required email configuration: {', '.join(missing_vars)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    return {
        'MAIL_SERVER': 'smtp.gmail.com',
        'MAIL_PORT': 587,
        'MAIL_USE_TLS': True,
        'MAIL_USE_SSL': False,
        'MAIL_USERNAME': os.getenv('MAIL_USERNAME'),
        'MAIL_PASSWORD': os.getenv('MAIL_PASSWORD'),
        'MAIL_DEFAULT_SENDER': os.getenv('MAIL_USERNAME'),
        'MAIL_MAX_EMAILS': None,
        'MAIL_SUPPRESS_SEND': False,
        'MAIL_ASCII_ATTACHMENTS': False,
        'BASE_URL': os.getenv('BASE_URL', 'http://localhost:5000')
    }

# Apply email configuration with error handling
try:
    app.config.update(configure_email())
    logger.info("Email configuration loaded successfully")
except Exception as e:
    logger.error(f"Failed to configure email settings: {str(e)}")
    raise

# Initialize extensions
db.init_app(app)
mail.init_app(app)

@app.route('/')
def index():
    return render_template('index.html')

def validate_contact_form(data):
    """Validate contact form data"""
    errors = {}
    
    # Name validation (2-100 characters, letters and spaces only)
    if not data.get('nombre') or not re.match("^[A-Za-zÀ-ÿ\s]{2,100}$", data['nombre']):
        errors['nombre'] = "Por favor, ingresa un nombre válido (2-100 caracteres)"
    
    # Email validation
    if not data.get('email') or not re.match(r"[^@]+@[^@]+\.[^@]+", data['email']):
        errors['email'] = "Por favor, ingresa un email válido"
    
    # Phone validation (Spanish phone number format)
    if not data.get('telefono') or not re.match(r"^(?:\+34|0034|34)?[6789]\d{8}$", data['telefono']):
        errors['telefono'] = "Por favor, ingresa un número de teléfono válido"
    
    # Message validation (required, max 1000 characters)
    if not data.get('dudas') or len(data['dudas']) > 1000:
        errors['dudas'] = "Por favor, ingresa un mensaje válido (máximo 1000 caracteres)"
    
    return errors

@app.route('/api/contact', methods=['POST'])
def contact():
    """Handle contact form submissions"""
    try:
        # Get form data
        data = request.json
        if not data:
            return jsonify({
                "error": "No se recibieron datos",
                "detail": "Por favor, completa el formulario"
            }), 400
        
        # Validate form data
        validation_errors = validate_contact_form(data)
        if validation_errors:
            return jsonify({
                "error": "Error de validación",
                "validation_errors": validation_errors
            }), 400
        
        # Send notification emails
        try:
            send_contact_form_notification(data)
            return jsonify({
                "message": "Mensaje enviado con éxito",
                "detail": "Te hemos enviado un correo de confirmación"
            }), 200
        except Exception as e:
            logger.error(f"Error sending contact form notification: {str(e)}")
            return jsonify({
                "error": "Error al enviar el mensaje",
                "detail": "Ha ocurrido un error al procesar tu solicitud. Por favor, inténtalo de nuevo más tarde."
            }), 500
            
    except Exception as e:
        logger.error(f"Error processing contact form: {str(e)}")
        return jsonify({
            "error": "Error del servidor",
            "detail": "Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo más tarde."
        }), 500

@app.route('/api/test-email', methods=['POST'])
def test_email():
    """Test route for email functionality"""
    try:
        # Verify email configuration
        if not app.config['MAIL_USERNAME'] or not app.config['MAIL_PASSWORD']:
            raise ValueError("Email configuration is incomplete")
        
        msg = Message(
            'Test Email',
            sender=app.config['MAIL_USERNAME'],
            recipients=[app.config['MAIL_USERNAME']]  # Send to self for testing
        )
        msg.body = "This is a test email to verify SMTP configuration"
        mail.send(msg)
        logger.info("Test email sent successfully")
        return jsonify({"message": "Test email sent successfully"}), 200
    except ValueError as e:
        logger.error(f"Email configuration error: {str(e)}")
        return jsonify({"error": "Email configuration is incomplete"}), 500
    except Exception as e:
        logger.error(f"Error sending test email: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}", exc_info=True)
    
    app.run(host='0.0.0.0', port=5000, debug=True)
