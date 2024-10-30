import os
from transformers import pipeline
from datetime import datetime, timedelta
import re
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from flask import session

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize models
MODEL_DIR = os.environ.get('MODEL_DIR', 'model')
os.makedirs(MODEL_DIR, exist_ok=True)

# Initialize models for different tasks
intent_classifier = pipeline(
    "text-classification",
    model="distilbert-base-uncased",
    num_labels=5,
    cache_dir=MODEL_DIR
)

# Available services and business hours
SERVICES = [
    'Desarrollo de IA',
    'Consultoría de IA',
    'Desarrollo Web'
]

BUSINESS_HOURS = {
    'start': '10:30',
    'end': '14:00'
}

# Metrics tracking
metrics = {
    "total_queries": 0,
    "successful_queries": 0,
    "response_times": [],
    "daily_stats": {}
}

def validate_name(name):
    """Validate full name with improved checks"""
    logger.debug(f"Validating name: {name}")
    if not name:
        return False, "Por favor, necesito tu nombre completo para continuar."
    
    name = name.strip()
    parts = name.split()
    
    if len(parts) < 2:
        return False, "Necesito tanto tu nombre como tus apellidos. Por ejemplo: 'Juan Pérez'"
    
    if any(len(part) < 2 for part in parts):
        return False, "Cada parte del nombre debe tener al menos 2 letras."
    
    if not all(part.isalpha() or "'" in part or "-" in part for part in parts):
        return False, "El nombre solo puede contener letras, apóstrofes y guiones."
    
    logger.debug(f"Name validation successful: {name}")
    return True, name

def validate_email(email):
    """Validate email format with improved validation"""
    logger.debug(f"Validating email: {email}")
    if not email:
        return False, "Por favor, proporciona un correo electrónico."
    
    email = email.strip().lower()
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    if not re.match(email_pattern, email):
        return False, "Por favor, proporciona un correo electrónico válido (ejemplo: nombre@dominio.com)"
    
    common_domains = ['gmail.com', 'yahoo.com', 'hotmail.com', 'outlook.com']
    domain = email.split('@')[1]
    
    for valid_domain in common_domains:
        if domain.startswith(valid_domain[:-4]) and domain != valid_domain:
            return False, f"¿Quisiste decir {email.split('@')[0]}@{valid_domain}?"
    
    logger.debug(f"Email validation successful: {email}")
    return True, email

def check_availability(date_str, time_str=None):
    """Check if date/time slot is available"""
    logger.debug(f"Checking availability for date: {date_str}, time: {time_str}")
    try:
        date = datetime.strptime(date_str, '%d/%m/%Y').date()
        
        if date.weekday() >= 5:
            return False, "Solo atendemos de lunes a viernes. ¿Podrías elegir otro día?"
        
        if date < datetime.now().date():
            return False, "La fecha seleccionada ya pasó. ¿Podrías elegir una fecha futura?"
        
        if time_str:
            time = datetime.strptime(time_str, '%H:%M').time()
            business_start = datetime.strptime(BUSINESS_HOURS['start'], '%H:%M').time()
            business_end = datetime.strptime(BUSINESS_HOURS['end'], '%H:%M').time()
            
            if time < business_start or time > business_end:
                return False, f"Nuestro horario de atención es de {BUSINESS_HOURS['start']} a {BUSINESS_HOURS['end']}. ¿Te gustaría elegir otro horario?"
            
            # Check if slot is already booked
            existing = Appointment.query.filter_by(date=date, time=time_str).first()
            if existing:
                return False, "Este horario ya está reservado. ¿Te gustaría ver otros horarios disponibles?"
        
        logger.debug("Slot is available")
        return True, "Horario disponible"
        
    except ValueError as e:
        logger.error(f"Availability check error: {str(e)}")
        return False, "Por favor, proporciona la fecha en formato dd/mm/yyyy y hora en formato HH:MM"

def create_appointment(data):
    """Create appointment from session data"""
    logger.debug("Creating appointment")
    try:
        # Create new appointment
        new_appointment = Appointment(
            name=data['name'],
            email=data['email'],
            service=data['service'],
            date=datetime.strptime(data['date'], '%d/%m/%Y').date(),
            time=data['time']
        )
        
        db.session.add(new_appointment)
        db.session.commit()
        
        # Send confirmation email
        send_appointment_confirmation(new_appointment)
        schedule_reminder_email(new_appointment)
        
        logger.debug(f"Appointment created successfully: {new_appointment.id}")
        return True, "¡Perfecto! Tu cita ha sido confirmada. Te he enviado un correo electrónico con todos los detalles."
    except Exception as e:
        logger.error(f"Error creating appointment: {str(e)}")
        db.session.rollback()
        return False, "Lo siento, ha ocurrido un error al reservar tu cita. ¿Podrías intentarlo nuevamente?"

def get_model_metrics():
    """Get current performance metrics"""
    if not metrics["response_times"]:
        return {
            "avg_response_time": 0,
            "success_rate": 0,
            "daily_queries": 0
        }
    
    avg_response_time = sum(metrics["response_times"]) / len(metrics["response_times"])
    success_rate = (metrics["successful_queries"] / metrics["total_queries"]) * 100 if metrics["total_queries"] > 0 else 0
    
    today = datetime.now().strftime("%Y-%m-%d")
    daily_queries = metrics["daily_stats"].get(today, {}).get("queries", 0)
    
    return {
        "avg_response_time": round(avg_response_time, 2),
        "success_rate": round(success_rate, 2),
        "daily_queries": daily_queries
    }

def update_metrics(start_time, success):
    """Update performance metrics"""
    end_time = datetime.now()
    response_time = (end_time - start_time).total_seconds() * 1000
    
    metrics["total_queries"] += 1
    if success:
        metrics["successful_queries"] += 1
    metrics["response_times"].append(response_time)
    
    today = end_time.strftime("%Y-%m-%d")
    if today not in metrics["daily_stats"]:
        metrics["daily_stats"][today] = {
            "queries": 0,
            "successful": 0,
            "avg_response_time": 0
        }
    
    daily_stats = metrics["daily_stats"][today]
    daily_stats["queries"] += 1
    if success:
        daily_stats["successful"] += 1
    daily_stats["avg_response_time"] = (
        (daily_stats["avg_response_time"] * (daily_stats["queries"] - 1) + response_time)
        / daily_stats["queries"]
    )

def generate_response(message):
    """Generate chatbot response"""
    start_time = datetime.now()
    try:
        company_name = os.environ.get('APP_NAME', 'Ingeniería IA')
        response = (f"¡Hola! Soy el asistente virtual de {company_name}. "
                  "¿Te gustaría agendar una cita con nosotros?")
        
        update_metrics(start_time, True)
        return response
        
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        update_metrics(start_time, False)
        return "Lo siento, ha ocurrido un error. ¿Podrías intentarlo de nuevo?"
