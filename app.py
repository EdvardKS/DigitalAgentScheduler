import os
from flask import Flask, render_template, request, jsonify, session
from datetime import datetime, time, timedelta
from chatbot import get_chat_response
from functools import wraps
from flask_mail import Mail
from email_utils import mail, send_appointment_confirmation, schedule_reminder_email
from models import db, Appointment
from sqlalchemy import func
import logging
from dotenv import load_dotenv
from appointments import AppointmentManager

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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/appointment')
def appointment():
    """Route for appointment booking page"""
    return render_template('appointment.html')

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
            response = get_chat_response(message, conversation_history)
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

@app.route('/api/book-appointment', methods=['POST'])
def book_appointment():
    """Endpoint for booking appointments"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        success, message, appointment = AppointmentManager.create_appointment(data)
        
        if success:
            return jsonify({
                "message": message,
                "appointment_id": appointment.id
            }), 201
        else:
            return jsonify({"error": message}), 400

    except Exception as e:
        logger.error(f"Error booking appointment: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/available-slots/<date>', methods=['GET'])
def get_available_slots(date):
    """Get available appointment slots for a given date"""
    try:
        slots = AppointmentManager.get_available_slots(date)
        return jsonify({"slots": slots})
    except Exception as e:
        logger.error(f"Error getting available slots: {str(e)}", exc_info=True)
        return jsonify({"error": "Error retrieving available slots"}), 500

@app.route('/api/appointments/<int:appointment_id>', methods=['DELETE'])
def cancel_appointment(appointment_id):
    """Cancel an existing appointment"""
    try:
        success, message = AppointmentManager.cancel_appointment(appointment_id)
        if success:
            return jsonify({"message": message}), 200
        return jsonify({"error": message}), 400
    except Exception as e:
        logger.error(f"Error cancelling appointment: {str(e)}", exc_info=True)
        return jsonify({"error": "Error cancelling appointment"}), 500

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}", exc_info=True)
    
    app.run(host='0.0.0.0', port=5000)
