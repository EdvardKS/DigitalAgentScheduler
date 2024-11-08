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

# Mail configuration with Gmail SMTP settings
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_MAX_EMAILS'] = None
app.config['MAIL_SUPPRESS_SEND'] = False
app.config['MAIL_ASCII_ATTACHMENTS'] = False
app.config['BASE_URL'] = os.getenv('BASE_URL', 'http://localhost:5000')

# Initialize extensions
db.init_app(app)
mail.init_app(app)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/test-email', methods=['POST'])
def test_email():
    """Test route for email functionality"""
    try:
        msg = Message(
            'Test Email',
            sender=app.config['MAIL_USERNAME'],
            recipients=[app.config['MAIL_USERNAME']]  # Send to self for testing
        )
        msg.body = "This is a test email to verify SMTP configuration"
        mail.send(msg)
        logger.info("Test email sent successfully")
        return jsonify({"message": "Test email sent successfully"}), 200
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
