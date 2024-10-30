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

# Initialize models for intent detection
MODEL_DIR = "model"
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

def extract_date(text):
    """Extract date from text with error handling"""
    logger.debug(f"Extracting date from: {text}")
    patterns = [
        r'(\d{1,2}/\d{1,2}/\d{4})',
        r'(\d{1,2}-\d{1,2}-\d{4})'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                date_str = match.group(1)
                date_parts = re.split('[/-]', date_str)
                date = datetime.strptime(f"{date_parts[0]}/{date_parts[1]}/{date_parts[2]}", "%d/%m/%Y")
                logger.debug(f"Successfully extracted date: {date.strftime('%d/%m/%Y')}")
                return date.strftime("%d/%m/%Y")
            except ValueError as e:
                logger.error(f"Date parsing error: {str(e)}")
                continue
    logger.debug("No valid date found")
    return None

def extract_time(text):
    """Extract time from text with error handling"""
    logger.debug(f"Extracting time from: {text}")
    time_pattern = r'(\d{1,2}:\d{2})'
    match = re.search(time_pattern, text)
    result = match.group(1) if match else None
    logger.debug(f"Extracted time: {result}")
    return result

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

def get_available_slots(date_str):
    """Get available time slots for a date"""
    logger.debug(f"Getting available slots for date: {date_str}")
    try:
        date = datetime.strptime(date_str, '%d/%m/%Y').date()
        if date.weekday() >= 5:
            return []
        
        slots = []
        current = datetime.strptime(BUSINESS_HOURS['start'], '%H:%M')
        end = datetime.strptime(BUSINESS_HOURS['end'], '%H:%M')
        
        while current <= end:
            time_str = current.strftime('%H:%M')
            existing = Appointment.query.filter_by(date=date, time=time_str).first()
            
            if not existing:
                slots.append(time_str)
            
            current += timedelta(minutes=30)
        
        logger.debug(f"Found available slots: {slots}")
        return slots
    except ValueError as e:
        logger.error(f"Error getting available slots: {str(e)}")
        return []

def create_appointment():
    """Create appointment from session data"""
    logger.debug("Creating appointment")
    try:
        data = session['booking']['data']
        
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

def get_step_prompt(step):
    """Get prompt for specific step"""
    prompts = {
        'name': "Por favor, proporciona tu nombre completo (nombre y apellidos)",
        'email': "¿Cuál es tu correo electrónico?",
        'service': f"¿Qué servicio te interesa?\n\nServicios disponibles:\n" + "\n".join([f"• {service}" for service in SERVICES]),
        'date': "¿Para qué fecha te gustaría la cita? (formato: dd/mm/yyyy)",
        'time': "¿Qué horario prefieres? (formato: HH:MM)"
    }
    return prompts.get(step, "¿En qué puedo ayudarte?")

def initialize_booking_session():
    """Initialize or reset booking session with proper structure and error handling"""
    logger.debug("Initializing booking session")
    try:
        session['booking'] = {
            'active': True,
            'step': 'name',
            'data': {
                'name': None,
                'email': None,
                'service': None,
                'date': None,
                'time': None
            },
            'attempts': {
                'name': 0,
                'email': 0,
                'service': 0,
                'date': 0,
                'time': 0
            },
            'previous_step': None
        }
        session.modified = True
        logger.debug(f"Session initialized successfully: {session.get('booking', {})}")
        return True
    except Exception as e:
        logger.error(f"Error initializing booking session: {str(e)}")
        return False

def validate_session_state():
    """Validate and repair session state if needed"""
    logger.debug("Validating session state")
    try:
        if 'booking' not in session:
            logger.warning("No booking session found, initializing new session")
            return initialize_booking_session()
            
        if 'attempts' not in session['booking']:
            logger.warning("Attempts not found in session, adding attempts structure")
            session['booking']['attempts'] = {
                'name': 0,
                'email': 0,
                'service': 0,
                'date': 0,
                'time': 0
            }
            session.modified = True
            
        if 'data' not in session['booking']:
            logger.warning("Data structure not found in session, adding data structure")
            session['booking']['data'] = {
                'name': None,
                'email': None,
                'service': None,
                'date': None,
                'time': None
            }
            session.modified = True
            
        if 'active' not in session['booking']:
            logger.warning("Active state not found in session, setting to True")
            session['booking']['active'] = True
            session.modified = True
            
        if 'step' not in session['booking']:
            logger.warning("Step not found in session, setting to 'name'")
            session['booking']['step'] = 'name'
            session.modified = True
            
        logger.debug("Session state validated successfully")
        return True
    except Exception as e:
        logger.error(f"Error validating session state: {str(e)}")
        return False

def handle_booking_step(message):
    """Handle booking steps with improved error handling and session validation"""
    logger.debug(f"Handling booking step with message: {message}")
    
    try:
        # Validate and repair session state
        if not validate_session_state():
            logger.error("Failed to validate session state")
            return "Lo siento, ha ocurrido un error. Por favor, intenta nuevamente."
        
        current_step = session['booking'].get('step', 'name')
        logger.debug(f"Current step: {current_step}")
        
        # Initialize attempts counter if needed
        if current_step not in session['booking']['attempts']:
            session['booking']['attempts'][current_step] = 0
            session.modified = True
        
        # Increment attempt counter
        session['booking']['attempts'][current_step] += 1
        session.modified = True
        
        # Handle navigation commands
        if message.lower() in ['atrás', 'volver', 'regresar']:
            if session['booking'].get('previous_step'):
                prev_step = session['booking']['previous_step']
                logger.debug(f"Moving back to previous step: {prev_step}")
                session['booking']['step'] = prev_step
                session.modified = True
                return get_step_prompt(prev_step)
            return "Estamos al inicio del proceso. ¿Deseas comenzar de nuevo? (responde 'reiniciar')"
        
        if message.lower() == 'reiniciar':
            logger.debug("Restarting booking process")
            if initialize_booking_session():
                return get_step_prompt('name')
            return "Lo siento, ha ocurrido un error al reiniciar. Por favor, intenta nuevamente."
        
        # Check max attempts
        max_attempts = 3
        if session['booking']['attempts'][current_step] > max_attempts:
            logger.warning(f"Maximum attempts reached for step: {current_step}")
            return ("Parece que estás teniendo dificultades. ¿Te gustaría:\n"
                   "1. Comenzar de nuevo (responde 'reiniciar')\n"
                   "2. Hablar con un asistente humano\n"
                   "3. Intentar de nuevo")
        
        # Handle step logic
        response = handle_step_logic(current_step, message)
        if response:
            return response
        
        logger.error("Unknown step or error in handling step")
        return "Lo siento, ha ocurrido un error. ¿Podrías intentarlo de nuevo?"
        
    except Exception as e:
        logger.error(f"Error in handle_booking_step: {str(e)}")
        return "Lo siento, ha ocurrido un error. Por favor, intenta nuevamente."

def handle_step_logic(current_step, message):
    """Handle the logic for each booking step"""
    logger.debug(f"Handling step logic for {current_step} with message: {message}")
    
    try:
        if current_step == 'name':
            is_valid, result = validate_name(message)
            if not is_valid:
                return result
            
            session['booking']['data']['name'] = result
            session['booking']['step'] = 'email'
            session['booking']['previous_step'] = 'name'
            session.modified = True
            
            first_name = result.split()[0]
            return f"Gracias {first_name}. ¿Podrías proporcionarme tu correo electrónico para enviarte la confirmación?"
        
        elif current_step == 'email':
            is_valid, result = validate_email(message)
            if not is_valid:
                return result
            
            session['booking']['data']['email'] = result
            session['booking']['step'] = 'service'
            session['booking']['previous_step'] = 'email'
            session.modified = True
            
            services_list = "\n".join([f"• {service}" for service in SERVICES])
            return f"Perfecto. ¿Qué servicio te interesa?\n\nServicios disponibles:\n{services_list}"
        
        elif current_step == 'service':
            if message not in SERVICES:
                services_list = "\n".join([f"• {service}" for service in SERVICES])
                return f"Por favor, elige uno de estos servicios:\n{services_list}"
            
            session['booking']['data']['service'] = message
            session['booking']['step'] = 'date'
            session['booking']['previous_step'] = 'service'
            session.modified = True
            
            return ("¿Para qué fecha te gustaría agendar la cita? (formato: dd/mm/yyyy)\n"
                    "Recuerda que atendemos de lunes a viernes.")
        
        elif current_step == 'date':
            date = extract_date(message)
            if not date:
                return "Por favor, indica la fecha en formato dd/mm/yyyy (ejemplo: 01/11/2024)"
            
            is_available, message_result = check_availability(date)
            if not is_available:
                return message_result
            
            slots = get_available_slots(date)
            if not slots:
                return f"Lo siento, no hay horarios disponibles para el {date}. ¿Te gustaría elegir otra fecha?"
            
            session['booking']['data']['date'] = date
            session['booking']['step'] = 'time'
            session['booking']['previous_step'] = 'date'
            session.modified = True
            
            slots_text = ", ".join(slots)
            return f"Excelente. Para el {date} tenemos estos horarios disponibles:\n{slots_text}\n\n¿Qué horario prefieres? (formato: HH:MM)"
        
        elif current_step == 'time':
            time = extract_time(message)
            if not time:
                return "Por favor, indica la hora en formato HH:MM (ejemplo: 10:30)"
            
            is_available, message_result = check_availability(session['booking']['data']['date'], time)
            if not is_available:
                return message_result
            
            session['booking']['data']['time'] = time
            session['booking']['step'] = 'confirmation'
            session['booking']['previous_step'] = 'time'
            session.modified = True
            
            booking_data = session['booking']['data']
            return (f"Por favor, confirma los detalles de tu cita:\n\n"
                    f"👤 Nombre: {booking_data['name']}\n"
                    f"📧 Email: {booking_data['email']}\n"
                    f"🔧 Servicio: {booking_data['service']}\n"
                    f"📅 Fecha: {booking_data['date']}\n"
                    f"⏰ Hora: {booking_data['time']}\n\n"
                    "¿Está todo correcto? (responde 'sí' para confirmar o 'no' para modificar)")
        
        elif current_step == 'confirmation':
            if message.lower() in ['sí', 'si', 'yes']:
                success, result = create_appointment()
                if success:
                    session.pop('booking', None)
                    session.modified = True
                return result
            elif message.lower() in ['no', 'modificar']:
                return ("¿Qué información deseas modificar?\n\n"
                       "1. Nombre\n"
                       "2. Email\n"
                       "3. Servicio\n"
                       "4. Fecha\n"
                       "5. Hora\n\n"
                       "Indica el número o nombre del campo a modificar")
            else:
                return "Por favor, responde 'sí' para confirmar o 'no' para modificar los detalles."
    
    except Exception as e:
        logger.error(f"Error in handle_step_logic: {str(e)}")
        return None

def get_intent(message):
    """Detect message intent with improved booking keywords"""
    logger.debug(f"Detecting intent for message: {message}")
    message = message.lower()
    
    booking_keywords = [
        'cita', 'reserva', 'agendar', 'reservar', 'consulta',
        'programar', 'quiero', 'necesito', 'solicitar', 'pedir'
    ]
    
    if any(word in message for word in booking_keywords):
        logger.debug("Booking intent detected via keywords")
        return 'booking'
    
    try:
        intent_text = intent_classifier(message)
        if isinstance(intent_text, list) and intent_text:
            result = intent_text[0]
        else:
            logger.warning("Intent classifier returned unexpected format")
            return 'unknown'
        
        logger.debug(f"Model classification result: {result}")
        
        intent_map = {
            0: 'booking',
            1: 'modification',
            2: 'cancellation',
            3: 'help',
            4: 'greeting'
        }
        
        if result.get('label') in intent_map:
            intent = intent_map[int(result.get('label'))]
            if result.get('score', 0) < 0.6:
                logger.debug("Low confidence score, falling back to keyword matching")
                modification_keywords = ['modificar', 'cambiar', 'editar', 'actualizar']
                cancellation_keywords = ['cancelar', 'eliminar', 'anular']
                help_keywords = ['ayuda', 'ayúdame', 'cómo', 'info']
                greeting_keywords = ['hola', 'buenos días', 'buenas']
                
                if any(word in message for word in modification_keywords):
                    intent = 'modification'
                elif any(word in message for word in cancellation_keywords):
                    intent = 'cancellation'
                elif any(word in message for word in help_keywords):
                    intent = 'help'
                elif any(word in message for word in greeting_keywords):
                    intent = 'greeting'
            
            logger.debug(f"Final intent: {intent}")
            return intent
            
        return 'unknown'
        
    except Exception as e:
        logger.error(f"Error in intent detection: {str(e)}")
        return 'unknown'

def generate_response(message):
    """Generate chatbot response with improved error handling"""
    start_time = datetime.now()
    logger.debug(f"Generating response for message: {message}")
    
    try:
        if 'booking' in session and session.get('booking', {}).get('active'):
            response = handle_booking_step(message)
        else:
            intent = get_intent(message)
            
            if intent == 'booking':
                initialize_booking_session()
                response = ("¡Hola! 👋 Me alegro de que quieras agendar una cita con nosotros. "
                          "Te ayudaré a programarla paso a paso.\n\n"
                          "Para empezar, ¿podrías proporcionarme tu nombre completo?")
            elif intent == 'modification':
                if 'booking' in session and session['booking'].get('step') == 'confirmation':
                    response = handle_booking_step(message)
                else:
                    response = "Para modificar una cita existente, por favor usa el enlace en tu correo de confirmación."
            elif intent == 'cancellation':
                response = "Para cancelar una cita, por favor usa el enlace en tu correo de confirmación."
            elif intent == 'help':
                response = ("Puedo ayudarte con lo siguiente:\n\n"
                          "1. Agendar una nueva cita\n"
                          "2. Informarte sobre nuestros servicios\n"
                          "3. Guiarte en el proceso de reserva\n\n"
                          "¿Qué te gustaría hacer?")
            elif intent == 'greeting':
                response = ("¡Hola! 👋 Soy el asistente virtual de Ingeniería IA.\n\n"
                          "¿Te gustaría agendar una cita con nosotros?")
            else:
                response = ("No estoy seguro de lo que necesitas. ¿Te gustaría:\n\n"
                          "1. Agendar una cita\n"
                          "2. Obtener información sobre nuestros servicios\n"
                          "3. Recibir ayuda con el proceso de reserva")
        
        update_metrics(start_time, True)
        logger.debug(f"Generated response: {response}")
        return response
        
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        update_metrics(start_time, False)
        return "Lo siento, ha ocurrido un error. ¿Podrías intentarlo de nuevo?"

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
    
    logger.debug(f"Updated metrics: {metrics}")

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
