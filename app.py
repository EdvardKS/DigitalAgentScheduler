import os
from flask import Flask, render_template, request, jsonify, session
from datetime import datetime, time, timedelta
from chatbot import generate_response, get_model_metrics
from functools import wraps
from flask_mail import Mail
from email_utils import mail, send_appointment_confirmation, schedule_reminder_email
from models import db, Appointment
from sqlalchemy import func

app = Flask(__name__)

# Basic configuration
app.secret_key = os.environ.get("FLASK_SECRET_KEY")
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Mail configuration
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 465))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'False').lower() == 'true'
app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['BASE_URL'] = os.environ.get('BASE_URL', 'http://localhost:5000')

# Initialize extensions
db.init_app(app)
mail.init_app(app)

from datetime import datetime
import holidays

# Get Elche holidays for the current and next year
this_year = datetime.now().year
next_year = this_year + 1

elche_holidays = holidays.Spain(years=[this_year, next_year])

# Extract Elche holidays as strings in 'YYYY-MM-DD' format
ELCHE_HOLIDAYS = [day.strftime('%Y-%m-%d') for day in elche_holidays if elche_holidays.get(day) == 'Elche']

# Business hours
BUSINESS_START = time(10, 30)  # 10:30 AM
BUSINESS_END = time(14, 0)    # 2:00 PM

def is_valid_appointment_time(date_str, time_str):
    """Validate appointment date and time"""
    try:
        # Convert date string to datetime
        appointment_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        appointment_time = datetime.strptime(time_str, '%H:%M').time()
        
        # Check if it's a holiday
        if date_str in ELCHE_HOLIDAYS:
            return False, "This date is a holiday in Elche. Please select another date."
        
        # Check if it's a weekend
        if appointment_date.weekday() >= 5:
            return False, "Appointments are only available Monday through Friday."
        
        # Check if time is within business hours
        if appointment_time < BUSINESS_START or appointment_time > BUSINESS_END:
            return False, "Appointments are only available between 10:30 AM and 2:00 PM."
        
        return True, ""
        
    except ValueError:
        return False, "Invalid date or time format."

def require_pin(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return jsonify({"error": "Authentication required"}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/appointment')
def appointment():
    return render_template('appointment.html')

@app.route('/analytics')
def analytics():
    return render_template('analytics.html')

@app.route('/mlops')
def mlops():
    return render_template('mlops.html')

@app.route('/api/verify-pin', methods=['POST'])
def verify_pin():
    data = request.get_json()
    if data.get('pin') == os.environ.get('CHATBOT_PIN', '1997'):
        session['authenticated'] = True
        return jsonify({"success": True})
    return jsonify({"success": False}), 401

@app.route('/api/analytics/appointments', methods=['GET'])
@require_pin
def get_appointment_analytics():
    today = datetime.now().date()
    month_start = today.replace(day=1)
    
    total = Appointment.query.count()
    
    monthly = Appointment.query.filter(
        Appointment.date >= month_start
    ).count()
    
    service_stats = db.session.query(
        Appointment.service,
        func.count(Appointment.id).label('count')
    ).group_by(Appointment.service).all()
    
    timeline_data = []
    for i in range(7):
        date = today - timedelta(days=i)
        count = Appointment.query.filter(Appointment.date == date).count()
        timeline_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'count': count
        })
    
    recent = Appointment.query.order_by(
        Appointment.date.desc()
    ).limit(5).all()
    
    return jsonify({
        'total': total,
        'monthly': monthly,
        'serviceLabels': [s[0] for s in service_stats],
        'serviceCounts': [s[1] for s in service_stats],
        'timelineLabels': [d['date'] for d in reversed(timeline_data)],
        'timelineCounts': [d['count'] for d in reversed(timeline_data)],
        'recent': [{
            'date': apt.date.strftime('%Y-%m-%d'),
            'time': apt.time,
            'service': apt.service
        } for apt in recent]
    })

@app.route('/api/analytics/inquiries', methods=['GET'])
@require_pin
def get_inquiry_analytics():
    metrics = get_model_metrics()
    
    today = datetime.now().date()
    timeline_data = []
    for i in range(7):
        date = today - timedelta(days=i)
        timeline_data.append({
            'date': date.strftime('%Y-%m-%d'),
            'count': metrics.get('daily_queries', 0)
        })
    
    return jsonify({
        'total': metrics.get('daily_queries', 0) * 7,
        'avgResponseTime': metrics.get('avg_response_time', 0),
        'successRate': metrics.get('success_rate', 0),
        'timelineLabels': [d['date'] for d in reversed(timeline_data)],
        'timelineCounts': [d['count'] for d in reversed(timeline_data)]
    })

@app.route('/api/book-appointment', methods=['POST'])
def book_appointment():
    data = request.get_json()
    
    is_valid, error_message = is_valid_appointment_time(data['date'], data['time'])
    if not is_valid:
        return jsonify({"error": error_message}), 400
    
    new_appointment = Appointment()
    new_appointment.name = data['name']
    new_appointment.email = data['email']
    new_appointment.date = datetime.strptime(data['date'], '%Y-%m-%d').date()
    new_appointment.time = data['time']
    new_appointment.service = data['service']
    
    try:
        db.session.add(new_appointment)
        db.session.commit()
        
        send_appointment_confirmation(new_appointment)
        schedule_reminder_email(new_appointment)
        
        return jsonify({"message": "Appointment booked successfully!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route('/api/chatbot', methods=['POST'])
def chatbot_response():
    data = request.get_json()
    message = data.get('message', '')
    conversation_history = data.get('conversation_history', [])
    
    response = generate_response(message, conversation_history)
    return jsonify({"response": response})

@app.route('/api/metrics', methods=['GET'])
@require_pin
def metrics():
    return jsonify(get_model_metrics())

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(host='0.0.0.0', port=5000)