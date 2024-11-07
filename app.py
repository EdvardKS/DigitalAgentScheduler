import os
from flask import Flask, render_template, request, jsonify, session
from datetime import datetime, time, timedelta
from chatbot import generate_response
from functools import wraps
from flask_mail import Mail, Message
from email_utils import mail, send_appointment_confirmation, schedule_reminder_email
from models import db, Appointment, Contact
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

def send_contact_confirmation_email(contact):
    """Send confirmation email for contact form submission"""
    try:
        msg = Message(
            'KIT CONSULTING - Confirmación de Contacto',
            sender=app.config['MAIL_USERNAME'],
            recipients=[contact.email]
        )
        
        # Prepare template context
        context = {
            'name': contact.name,
            'email': contact.email,
            'phone': contact.phone,
            'inquiry': contact.inquiry,
            'logo_url': f"{app.config['BASE_URL']}/static/disenyo/SVG/01-LOGO.svg"
        }
        
        msg.html = render_template('email/contact_confirmation.html', **context)
        
        # Send email
        mail.send(msg)
        logger.info(f"Contact confirmation email sent to {contact.email}")
        
    except Exception as e:
        logger.error(f"Error sending contact confirmation email: {str(e)}")
        raise

def check_rate_limit(ip):
    """Check if the request should be rate limited"""
    now = datetime.now()
    request_counts[ip] = [t for t in request_counts[ip] if now - t < timedelta(seconds=RATE_WINDOW)]
    request_counts[ip].append(now)
    return len(request_counts[ip]) <= RATE_LIMIT

# Validation functions
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

# Routes
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

@app.route('/api/contacts', methods=['GET'])
@require_pin
def get_contacts():
    try:
        logger.info("Fetching contacts from database")
        contacts = Contact.query.order_by(Contact.created_at.desc()).all()
        logger.info(f"Found {len(contacts)} contacts")
        
        contacts_list = []
        for contact in contacts:
            contact_data = {
                'id': contact.id,
                'name': contact.name,
                'email': contact.email,
                'phone': contact.phone,
                'postal_code': contact.postal_code,
                'city': contact.city,
                'province': contact.province,
                'inquiry': contact.inquiry,
                'status': contact.status,
                'created_at': contact.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
            contacts_list.append(contact_data)
            logger.debug(f"Processed contact: {contact_data}")
        
        return jsonify({"contacts": contacts_list})
    except Exception as e:
        logger.error(f"Error fetching contacts: {str(e)}", exc_info=True)
        return jsonify({"error": "Error fetching contacts", "details": str(e)}), 500

@app.route('/api/contacts/<int:contact_id>', methods=['PUT'])
@require_pin
def update_contact(contact_id):
    try:
        contact = Contact.query.get(contact_id)
        if not contact:
            return jsonify({"error": "Contact not found"}), 404
        
        data = request.get_json()
        contact.status = data.get('status', contact.status)
        
        db.session.commit()
        logger.info(f"Contact {contact_id} updated successfully")
        
        return jsonify({"message": "Contact updated successfully"})
    except Exception as e:
        logger.error(f"Error updating contact: {str(e)}")
        return jsonify({"error": "Error updating contact"}), 500

@app.route('/api/contact', methods=['POST'])
def handle_contact_form():
    try:
        data = request.get_json()
        
        # Validate required fields
        required_fields = ['nombre', 'email', 'telefono']
        for field in required_fields:
            if not data.get(field):
                return jsonify({"error": f"Campo requerido: {field}"}), 400

        # Create new contact
        contact = Contact(
            name=data['nombre'],
            email=data['email'],
            phone=data['telefono'],
            postal_code=data.get('codigoPostal'),
            city=data.get('ciudad'),
            province=data.get('provincia'),
            inquiry=data.get('dudas'),
            status='Nuevo',
            created_at=datetime.utcnow()
        )

        db.session.add(contact)
        db.session.commit()
        logger.info(f"New contact form submission created: {contact.id}")
        
        # Send confirmation email
        try:
            send_contact_confirmation_email(contact)
        except Exception as e:
            logger.error(f"Failed to send confirmation email: {str(e)}")
            # Continue execution even if email fails
        
        return jsonify({"message": "Formulario enviado exitosamente"}), 200

    except Exception as e:
        logger.error(f"Error processing contact form: {str(e)}")
        return jsonify({"error": "Error al procesar el formulario"}), 500

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