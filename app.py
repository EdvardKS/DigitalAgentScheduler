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

app = Flask(__name__)

# Enhanced configuration with improved session settings
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

def check_ip_block(ip):
    """Check if an IP is blocked and handle failed attempts"""
    try:
        result = db.session.execute(text("""
            SELECT failed_attempts, blocked_until 
            FROM ip_blocks 
            WHERE ip_address = :ip
        """), {"ip": ip}).fetchone()

        if result:
            failed_attempts, blocked_until = result

            # If blocked and block period hasn't expired
            if blocked_until and blocked_until > datetime.now():
                remaining_time = int((blocked_until - datetime.now()).total_seconds() / 60)
                return False, remaining_time

            # If block has expired, reset the record
            if blocked_until and blocked_until <= datetime.now():
                db.session.execute(text("""
                    UPDATE ip_blocks 
                    SET failed_attempts = 0, blocked_until = NULL 
                    WHERE ip_address = :ip
                """), {"ip": ip})
                db.session.commit()
                return True, 0

        return True, 0

    except Exception as e:
        logger.error(f"Error checking IP block: {str(e)}")
        return True, 0  # Allow access in case of database errors

def record_failed_attempt(ip):
    """Record a failed PIN attempt and block IP if necessary"""
    try:
        # Insert or update the record
        db.session.execute(text("""
            INSERT INTO ip_blocks (ip_address, failed_attempts, last_attempt)
            VALUES (:ip, 1, NOW())
            ON CONFLICT (ip_address) 
            DO UPDATE SET 
                failed_attempts = ip_blocks.failed_attempts + 1,
                last_attempt = NOW(),
                blocked_until = CASE 
                    WHEN ip_blocks.failed_attempts + 1 >= :max_attempts 
                    THEN NOW() + interval ':block_minutes minutes'
                    ELSE NULL 
                END;
        """), {
            "ip": ip, 
            "max_attempts": MAX_FAILED_ATTEMPTS,
            "block_minutes": BLOCK_DURATION
        })
        db.session.commit()

        # Get updated record
        result = db.session.execute(text("""
            SELECT failed_attempts, blocked_until 
            FROM ip_blocks 
            WHERE ip_address = :ip
        """), {"ip": ip}).fetchone()

        if result and result[0] >= MAX_FAILED_ATTEMPTS:
            return False, BLOCK_DURATION
        return True, 0

    except Exception as e:
        logger.error(f"Error recording failed attempt: {str(e)}")
        return True, 0

def reset_failed_attempts(ip):
    """Reset failed attempts for an IP after successful login"""
    try:
        db.session.execute(text("""
            DELETE FROM ip_blocks 
            WHERE ip_address = :ip
        """), {"ip": ip})
        db.session.commit()
    except Exception as e:
        logger.error(f"Error resetting failed attempts: {str(e)}")

def check_rate_limit(ip):
    """Check if the request should be rate limited"""
    now = datetime.now()
    request_counts[ip] = [t for t in request_counts[ip] if now - t < timedelta(seconds=RATE_WINDOW)]
    request_counts[ip].append(now)
    return len(request_counts[ip]) <= RATE_LIMIT

# Enhanced PIN protection decorator with session refresh
def require_pin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('pin_verified'):
            logger.warning("Unauthorized access attempt - PIN verification required")
            return jsonify({"error": "Unauthorized", "code": "AUTH_REQUIRED"}), 401
        
        # Refresh session if it's permanent
        if session.get('remember_me'):
            session.modified = True
            session.permanent = True
        
        return f(*args, **kwargs)
    return decorated_function

# Main routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/citas')
def appointment_management():
    return render_template('appointment_management.html')

# Session check endpoint with enhanced session info
@app.route('/api/check-session')
def check_session():
    is_authenticated = bool(session.get('pin_verified'))
    remember_me = bool(session.get('remember_me'))
    
    # Refresh session if remember_me is enabled and authenticated
    if is_authenticated and remember_me:
        session.modified = True
        session.permanent = True
    
    return jsonify({
        "authenticated": is_authenticated,
        "remember_me": remember_me
    })

# Enhanced PIN verification endpoint with improved session handling
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
            
            # Set session permanence and remember_me flag
            session.permanent = remember_me
            session['remember_me'] = remember_me
            session['pin_verified'] = True
            session['pin_timestamp'] = datetime.now().timestamp()
            
            reset_failed_attempts(ip)
            logger.info("PIN verification successful")
            
            response = jsonify({
                "success": True,
                "remember_me": remember_me
            })
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
        response.set_cookie(app.config['SESSION_COOKIE_NAME'], '', expires=0)
        
        logger.info("User logged out successfully")
        return response
    except Exception as e:
        logger.error(f"Error during logout: {str(e)}")
        return jsonify({"success": False, "error": "Error during logout"}), 500

if __name__ == "__main__":
    with app.app_context():
        try:
            db.create_all()
            logger.info("Database tables created successfully")
        except Exception as e:
            logger.error(f"Error creating database tables: {e}")

    app.run(host='0.0.0.0', port=5000)
