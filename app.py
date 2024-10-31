import os
from flask import Flask, render_template, request, jsonify, session
from datetime import datetime, time, timedelta
from chatbot import generate_response, get_model_metrics
from functools import wraps
from flask_mail import Mail
from email_utils import mail, send_appointment_confirmation, schedule_reminder_email
from models import db, Appointment
from sqlalchemy import func
import logging
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

def check_appointment_availability(date, time):
    """Check if the requested appointment slot is available"""
    try:
        existing_appointment = Appointment.query.filter_by(
            date=date,
            time=time
        ).first()
        
        # Check if date is a weekend
        appointment_date = datetime.strptime(date, '%Y-%m-%d')
        if appointment_date.weekday() >= 5:
            return False, "No disponible en fin de semana"
            
        # Check if time is within business hours (10:30 AM - 2:00 PM)
        appointment_time = datetime.strptime(time, '%H:%M').time()
        if appointment_time < time(10, 30) or appointment_time > time(14, 0):
            return False, "Fuera del horario de atención (10:30 - 14:00)"
            
        return not bool(existing_appointment), None
        
    except Exception as e:
        logger.error(f"Error checking appointment availability: {str(e)}")
        return False, "Error al verificar disponibilidad"

@app.route('/api/appointments/check', methods=['POST'])
def check_availability():
    """API endpoint to check appointment availability"""
    try:
        data = request.get_json()
        date = data.get('date')
        time_slot = data.get('time')
        
        if not date or not time_slot:
            return jsonify({'error': 'Fecha y hora requeridas'}), 400
            
        is_available, error_message = check_appointment_availability(date, time_slot)
        
        return jsonify({
            'available': is_available,
            'error': error_message
        })
        
    except Exception as e:
        logger.error(f"Error in check_availability endpoint: {str(e)}")
        return jsonify({'error': 'Error al verificar disponibilidad'}), 500

@app.route('/api/appointments/schedule', methods=['POST'])
def schedule_appointment():
    """API endpoint to schedule an appointment"""
    try:
        data = request.get_json()
        required_fields = ['name', 'email', 'date', 'time', 'service']
        
        # Validate required fields
        if not all(field in data for field in required_fields):
            return jsonify({'error': 'Todos los campos son requeridos'}), 400
            
        # Check availability
        is_available, error_message = check_appointment_availability(data['date'], data['time'])
        if not is_available:
            return jsonify({'error': error_message or 'Horario no disponible'}), 400
            
        # Create appointment
        appointment = Appointment(
            name=data['name'],
            email=data['email'],
            date=datetime.strptime(data['date'], '%Y-%m-%d').date(),
            time=data['time'],
            service=data['service']
        )
        
        db.session.add(appointment)
        db.session.commit()
        
        # Send confirmation email
        try:
            send_appointment_confirmation(appointment)
            schedule_reminder_email(appointment)
        except Exception as e:
            logger.error(f"Error sending confirmation email: {str(e)}")
            # Don't return error to client, appointment was still created
            
        return jsonify({
            'message': 'Cita agendada exitosamente',
            'appointment_id': appointment.id
        })
        
    except Exception as e:
        logger.error(f"Error in schedule_appointment endpoint: {str(e)}")
        return jsonify({'error': 'Error al agendar la cita'}), 500

@app.route('/')
def index():
    return render_template('index.html')

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
