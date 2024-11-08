import os
from flask import Flask, render_template, request, jsonify, session, make_response
from datetime import datetime, time, timedelta
from chatbot import generate_response
from functools import wraps
from flask_mail import Mail
from email_utils import mail, send_appointment_confirmation, schedule_reminder_email, send_contact_form_notification
from models import db, Appointment, ContactSubmission
from sqlalchemy import func, text
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
MAX_FAILED_ATTEMPTS = 2  # Maximum failed PIN attempts before blocking
BLOCK_DURATION = 30  # Block duration in minutes
SESSION_DURATION = timedelta(days=7)  # Session duration for remember me

# IP blocking functions
def check_ip_block(ip):
    try:
        # Check if ip_blocks table exists, create if not
        db.session.execute(text('''
            CREATE TABLE IF NOT EXISTS ip_blocks (
                ip_address VARCHAR(45) PRIMARY KEY,
                failed_attempts INTEGER DEFAULT 0,
                last_attempt TIMESTAMP,
                blocked_until TIMESTAMP
            )
        '''))
        db.session.commit()
        
        result = db.session.execute(text('''
            SELECT failed_attempts, blocked_until 
            FROM ip_blocks 
            WHERE ip_address = :ip
        '''), {'ip': ip}).fetchone()
        
        if result and result.blocked_until:
            now = datetime.now()
            if now < result.blocked_until:
                remaining = int((result.blocked_until - now).total_seconds() / 60)
                return False, remaining
            else:
                # Reset if block has expired
                reset_failed_attempts(ip)
                return True, 0
                
        return True, 0
        
    except Exception as e:
        logger.error(f"Error checking IP block: {e}")
        return True, 0  # Allow on error to prevent lockout

def record_failed_attempt(ip):
    try:
        result = db.session.execute(text('''
            INSERT INTO ip_blocks (ip_address, failed_attempts, last_attempt)
            VALUES (:ip, 1, :now)
            ON CONFLICT (ip_address) DO UPDATE
            SET failed_attempts = ip_blocks.failed_attempts + 1,
                last_attempt = :now,
                blocked_until = CASE 
                    WHEN ip_blocks.failed_attempts + 1 >= :max_attempts 
                    THEN :block_until
                    ELSE NULL
                END
            RETURNING failed_attempts, blocked_until
        '''), {
            'ip': ip,
            'now': datetime.now(),
            'max_attempts': MAX_FAILED_ATTEMPTS,
            'block_until': datetime.now() + timedelta(minutes=BLOCK_DURATION)
        }).fetchone()
        
        db.session.commit()
        
        if result.failed_attempts >= MAX_FAILED_ATTEMPTS:
            return False, BLOCK_DURATION
            
        return True, 0
        
    except Exception as e:
        logger.error(f"Error recording failed attempt: {e}")
        return True, 0

def reset_failed_attempts(ip):
    try:
        db.session.execute(text('''
            DELETE FROM ip_blocks
            WHERE ip_address = :ip
        '''), {'ip': ip})
        db.session.commit()
    except Exception as e:
        logger.error(f"Error resetting failed attempts: {e}")

app = Flask(__name__)

# Enhanced configuration with improved session settings
app.config.update(
    SECRET_KEY=os.getenv("FLASK_SECRET_KEY"),
    SQLALCHEMY_DATABASE_URI=os.getenv("DATABASE_URL"),
    SQLALCHEMY_ENGINE_OPTIONS={
        "pool_recycle": 300,
        "pool_pre_ping": True,
    },
    PERMANENT_SESSION_LIFETIME=SESSION_DURATION,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_NAME='kit_session',
    SESSION_COOKIE_PATH='/',
    SESSION_REFRESH_EACH_REQUEST=True
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

def validate_session():
    """Validate the current session and return its status"""
    if not session.get('pin_verified'):
        return False, False
    
    # Check session timestamp
    timestamp = session.get('pin_timestamp')
    if not timestamp:
        return False, False
    
    session_age = datetime.now().timestamp() - timestamp
    remember_me = session.get('remember_me', False)
    
    # For non-remembered sessions, use a shorter timeout (2 hours)
    max_age = SESSION_DURATION.total_seconds() if remember_me else 7200  # 2 hours
    
    if session_age > max_age:
        return False, remember_me
        
    return True, remember_me

def extend_session():
    """Extend the session if it's valid"""
    session['pin_timestamp'] = datetime.now().timestamp()
    if session.get('remember_me'):
        session.permanent = True
        session.modified = True

# Session check endpoint with enhanced validation
@app.route('/api/check-session')
def check_session():
    is_valid, was_remembered = validate_session()
    
    if not is_valid:
        # Clear invalid session
        session.clear()
        return jsonify({
            "authenticated": False,
            "remember_me": False,
            "session_expired": True
        })
    
    # Extend valid session
    extend_session()
    
    return jsonify({
        "authenticated": True,
        "remember_me": was_remembered
    })

# Enhanced PIN verification endpoint
@app.route('/api/verify-pin', methods=['POST'])
def verify_pin():
    try:
        data = request.get_json()
        pin = data.get('pin')
        remember_me = bool(data.get('remember_me', False))
        correct_pin = os.getenv('CHATBOT_PIN')
        ip = request.remote_addr

        # Check if IP is blocked
        allowed, block_minutes = check_ip_block(ip)
        if not allowed:
            logger.warning(f"Blocked IP {ip} attempted to verify PIN")
            return jsonify({
                "success": False, 
                "error": f"Demasiados intentos fallidos. Por favor, espere {block_minutes} minutos."
            }), 429

        if not pin or not correct_pin:
            logger.warning("Missing PIN in verification attempt")
            return jsonify({"success": False, "error": "PIN inválido"}), 400
        
        if pin == correct_pin:
            # Clear any existing session data
            session.clear()
            
            # Set up new session
            session.permanent = remember_me
            session['remember_me'] = remember_me
            session['pin_verified'] = True
            session['pin_timestamp'] = datetime.now().timestamp()
            
            # Set cookie attributes
            response = jsonify({
                "success": True,
                "remember_me": remember_me
            })
            
            if remember_me:
                # Set secure cookie with proper expiration
                expires = datetime.now() + SESSION_DURATION
                response.set_cookie(
                    app.config['SESSION_COOKIE_NAME'],
                    session.get('_id', ''),
                    expires=expires,
                    secure=True,
                    httponly=True,
                    samesite='Lax'
                )
            
            reset_failed_attempts(ip)
            logger.info("PIN verification successful")
            return response
        
        # Record failed attempt
        allowed, block_minutes = record_failed_attempt(ip)
        if not allowed:
            logger.warning(f"IP {ip} blocked after too many failed attempts")
            return jsonify({
                "success": False,
                "error": f"Demasiados intentos fallidos. Por favor, espere {block_minutes} minutos."
            }), 429

        logger.warning("Invalid PIN attempt")
        return jsonify({"success": False, "error": "PIN inválido"}), 401
        
    except Exception as e:
        logger.error(f"Error in PIN verification: {str(e)}")
        return jsonify({"success": False, "error": "Error de servidor"}), 500

# Enhanced logout endpoint with proper session cleanup
@app.route('/api/logout', methods=['POST'])
def logout():
    try:
        # Store remember_me status before clearing
        was_remembered = session.get('remember_me', False)
        
        # Clear the entire session
        session.clear()
        
        # Create response
        response = jsonify({
            "success": True,
            "was_remembered": was_remembered
        })
        
        # Clear session cookie by setting it to expire immediately
        response.set_cookie(
            app.config['SESSION_COOKIE_NAME'],
            '',
            expires=0,
            secure=True,
            httponly=True,
            samesite='Lax'
        )
        
        logger.info("User logged out successfully")
        return response
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

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")

    app.run(host='0.0.0.0', port=5000)
