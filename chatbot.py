import os
import openai
from datetime import datetime, timedelta
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

# Set up enhanced logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Validate OpenAI API key
openai.api_key = os.getenv('OPENAI_API_KEY')
if not openai.api_key:
    logger.error("OpenAI API key not found in environment variables")
    raise ValueError("OpenAI API key is required")

# Metrics tracking
metrics = {
    "total_queries": 0,
    "successful_queries": 0,
    "failed_queries": 0,
    "response_times": [],
    "daily_stats": {},
    "error_types": {}
}

# Appointment Management Constants
AVAILABLE_HOURS = ["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00"]
MAX_DAYS_AHEAD = 30

# Navegatel and KIT CONSULTING Information
COMPANY_INFO = """
Somos Navegatel, una empresa especializada en asesoría digital, expertos en el programa KIT CONSULTING. El KIT CONSULTING es un programa de ayudas del Gobierno de España que permite a pymes diseñar la hoja de ruta para su transformación digital.

Servicios principales:
1. Inteligencia Artificial - hasta 6.000€
2. Ventas Digitales - hasta 6.000€
3. Estrategia y Rendimiento de Negocio - hasta 6.000€

Horario de citas:
- Lunes a Viernes
- De 10:30 a 14:00
- No disponible en festivos de Elche

Para agendar una cita, necesitaré:
- Tu nombre completo
- Email
- Servicio de interés
- Fecha y hora preferida

IMPORTANTE:
- Responde solo ha preguntas relacionadas con el KIT CONSULTING o servicios de Navegatel.
- Somos especialistas en Inteligencia Artificial, Ventas Digitales y Estrategia y Rendimiento de Negocio.
- Para contacto directo: info@navegatel.org o 673 66 09 10
"""

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_name(name):
    """Validate name format"""
    return bool(name and len(name.split()) >= 2 and all(part.isalpha() for part in name.split()))

def validate_service(service):
    """Validate service selection"""
    valid_services = ["Inteligencia Artificial", "Ventas Digitales", "Estrategia y Rendimiento de Negocio"]
    return service in valid_services

def validate_date(date_str):
    """Validate appointment date"""
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        max_date = today + timedelta(days=MAX_DAYS_AHEAD)
        
        # Check if date is within valid range and is a weekday
        if today <= date <= max_date and date.weekday() < 5:
            return True
        return False
    except ValueError:
        return False

def validate_time(time_str):
    """Validate appointment time"""
    return time_str in AVAILABLE_HOURS

def check_appointment_availability(date, time):
    """Check if the time slot is available"""
    try:
        existing_appointment = Appointment.query.filter_by(
            date=datetime.strptime(date, '%Y-%m-%d').date(),
            time=time
        ).first()
        return existing_appointment is None
    except Exception as e:
        logger.error(f"Error checking appointment availability: {str(e)}")
        return False

def create_appointment(name, email, service, date, time):
    """Create a new appointment"""
    try:
        appointment = Appointment(
            name=name,
            email=email,
            service=service,
            date=datetime.strptime(date, '%Y-%m-%d').date(),
            time=time
        )
        db.session.add(appointment)
        db.session.commit()
        
        # Send confirmation email and schedule reminder
        send_appointment_confirmation(appointment)
        schedule_reminder_email(appointment)
        
        return True, appointment
    except Exception as e:
        logger.error(f"Error creating appointment: {str(e)}")
        db.session.rollback()
        return False, None

def get_appointment_status(conversation_history):
    """Track appointment booking progress from conversation"""
    appointment_data = {
        'name': None,
        'email': None,
        'service': None,
        'date': None,
        'time': None,
        'stage': 'initial'
    }
    
    for msg in conversation_history:
        if not msg.get('is_user', False):
            continue
            
        text = msg['text'].lower()
        
        # Extract name if provided
        if 'me llamo' in text or 'mi nombre es' in text:
            potential_name = text.split('llamo ')[-1].split('nombre es ')[-1].strip().title()
            if validate_name(potential_name):
                appointment_data['name'] = potential_name
                
        # Extract email if provided
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
        if email_match and validate_email(email_match.group(0)):
            appointment_data['email'] = email_match.group(0)
            
        # Extract service if mentioned
        for service in ["Inteligencia Artificial", "Ventas Digitales", "Estrategia"]:
            if service.lower() in text:
                appointment_data['service'] = service
                break
                
        # Extract date if provided
        date_match = re.search(r'\d{4}-\d{2}-\d{2}', text)
        if date_match and validate_date(date_match.group(0)):
            appointment_data['date'] = date_match.group(0)
            
        # Extract time if provided
        for time in AVAILABLE_HOURS:
            if time in text:
                appointment_data['time'] = time
                break
    
    # Determine current stage
    if not appointment_data['name']:
        appointment_data['stage'] = 'need_name'
    elif not appointment_data['email']:
        appointment_data['stage'] = 'need_email'
    elif not appointment_data['service']:
        appointment_data['stage'] = 'need_service'
    elif not appointment_data['date']:
        appointment_data['stage'] = 'need_date'
    elif not appointment_data['time']:
        appointment_data['stage'] = 'need_time'
    else:
        appointment_data['stage'] = 'complete'
    
    return appointment_data

def handle_appointment_booking(message, conversation_history):
    """Handle appointment booking conversation flow"""
    appointment_status = get_appointment_status(conversation_history)
    
    if appointment_status['stage'] == 'need_name':
        return """Para comenzar con la reserva de tu cita, necesito tu nombre completo.
Por favor, escríbelo en el formato: 'Me llamo [Nombre Apellidos]'"""
    
    elif appointment_status['stage'] == 'need_email':
        return """Gracias. Ahora necesito tu correo electrónico para enviarte la confirmación.
Por favor, compártelo conmigo."""
    
    elif appointment_status['stage'] == 'need_service':
        return """¿Qué servicio te interesa consultar?
1. Inteligencia Artificial
2. Ventas Digitales
3. Estrategia y Rendimiento de Negocio
Por favor, indica el nombre del servicio."""
    
    elif appointment_status['stage'] == 'need_date':
        today = datetime.now().date()
        available_dates = []
        for i in range(MAX_DAYS_AHEAD):
            check_date = today + timedelta(days=i)
            if check_date.weekday() < 5:  # Monday to Friday
                available_dates.append(check_date.strftime('%Y-%m-%d'))
        
        return f"""¿Qué día te gustaría programar la cita? 
Fechas disponibles (formato YYYY-MM-DD):
{', '.join(available_dates[:5])}..."""
    
    elif appointment_status['stage'] == 'need_time':
        if not validate_date(appointment_status['date']):
            return "La fecha seleccionada no es válida. Por favor, elige una fecha entre las disponibles."
            
        available_times = []
        for time in AVAILABLE_HOURS:
            if check_appointment_availability(appointment_status['date'], time):
                available_times.append(time)
        
        return f"""¿Qué hora prefieres? Horarios disponibles:
{', '.join(available_times)}"""
    
    elif appointment_status['stage'] == 'complete':
        # Validate all data before creating appointment
        if not all([
            validate_name(appointment_status['name']),
            validate_email(appointment_status['email']),
            validate_service(appointment_status['service']),
            validate_date(appointment_status['date']),
            validate_time(appointment_status['time'])
        ]):
            return "Lo siento, hay algunos datos inválidos. Empecemos de nuevo con la reserva."
        
        # Check final availability
        if not check_appointment_availability(appointment_status['date'], appointment_status['time']):
            return "Lo siento, ese horario ya no está disponible. Por favor, elige otro horario."
        
        # Create appointment
        success, appointment = create_appointment(
            appointment_status['name'],
            appointment_status['email'],
            appointment_status['service'],
            appointment_status['date'],
            appointment_status['time']
        )
        
        if success:
            return f"""¡Perfecto! Tu cita ha sido reservada con éxito:
Nombre: {appointment_status['name']}
Servicio: {appointment_status['service']}
Fecha: {appointment_status['date']}
Hora: {appointment_status['time']}

Te hemos enviado un correo de confirmación a {appointment_status['email']}.
Recibirás un recordatorio 24 horas antes de la cita."""
        else:
            return "Lo siento, ha ocurrido un error al reservar la cita. Por favor, inténtalo de nuevo o contáctanos directamente."
    
    return "Lo siento, no pude procesar tu solicitud. ¿Podrías intentarlo de nuevo?"

def get_chat_response(user_message, conversation_history=None):
    """Generate a response using OpenAI's ChatGPT with enhanced error handling"""
    try:
        logger.info(f"Processing chat request - Message length: {len(user_message)}")
        
        if not user_message.strip():
            logger.warning("Empty message received")
            return "Por favor, escribe tu pregunta para poder ayudarte."

        if conversation_history is None:
            conversation_history = []
            
        # Check if message indicates appointment booking intent
        appointment_keywords = ['cita', 'reserva', 'agendar', 'programar', 'consulta']
        is_appointment_request = any(keyword in user_message.lower() for keyword in appointment_keywords)
        
        if is_appointment_request:
            return handle_appointment_booking(user_message, conversation_history)

        # Prepare the conversation with system context
        messages = [
            {
                "role": "system",
                "content": f"Eres el asistente virtual de Navegatel, especializado en el programa KIT CONSULTING. Tu objetivo es ayudar a los usuarios a entender el programa de ayudas y guiarlos en el proceso de solicitud. Aquí está la información clave: {COMPANY_INFO}"
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            messages.append({"role": "user" if msg["is_user"] else "assistant", "content": msg["text"]})

        # Add the current message
        messages.append({"role": "user", "content": user_message})

        # Get response from OpenAI with timeout handling
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
            top_p=0.9,
            presence_penalty=0.6,
            frequency_penalty=0.3
        )
        
        logger.info("Successfully received response from OpenAI")
        return response.choices[0].message["content"]

    except Exception as e:
        logger.error(f"Error in get_chat_response: {str(e)}", exc_info=True)
        metrics["error_types"][type(e).__name__] = metrics["error_types"].get(type(e).__name__, 0) + 1
        return "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo más tarde."

def get_model_metrics():
    """Get current performance metrics"""
    try:
        if not metrics["response_times"]:
            return {
                "avg_response_time": 0,
                "success_rate": 0,
                "daily_queries": 0,
                "error_rate": 0,
                "common_errors": []
            }
        
        avg_response_time = sum(metrics["response_times"]) / len(metrics["response_times"])
        success_rate = (metrics["successful_queries"] / metrics["total_queries"]) * 100 if metrics["total_queries"] > 0 else 0
        error_rate = (metrics["failed_queries"] / metrics["total_queries"]) * 100 if metrics["total_queries"] > 0 else 0
        
        today = datetime.now().strftime("%Y-%m-%d")
        daily_queries = metrics["daily_stats"].get(today, {}).get("queries", 0)
        
        common_errors = sorted(
            metrics["error_types"].items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]
        
        return {
            "avg_response_time": round(avg_response_time, 2),
            "success_rate": round(success_rate, 2),
            "error_rate": round(error_rate, 2),
            "daily_queries": daily_queries,
            "common_errors": common_errors
        }
    except Exception as e:
        logger.error(f"Error getting metrics: {str(e)}", exc_info=True)
        return {
            "error": "Error retrieving metrics",
            "details": str(e)
        }

def update_metrics(start_time, success):
    """Update performance metrics"""
    try:
        end_time = datetime.now()
        response_time = (end_time - start_time).total_seconds() * 1000
        
        metrics["total_queries"] += 1
        if success:
            metrics["successful_queries"] += 1
        else:
            metrics["failed_queries"] += 1
        
        metrics["response_times"].append(response_time)
        
        today = end_time.strftime("%Y-%m-%d")
        if today not in metrics["daily_stats"]:
            metrics["daily_stats"][today] = {
                "queries": 0,
                "successful": 0,
                "failed": 0,
                "avg_response_time": 0
            }
        
        daily_stats = metrics["daily_stats"][today]
        daily_stats["queries"] += 1
        if success:
            daily_stats["successful"] += 1
        else:
            daily_stats["failed"] += 1
            
        daily_stats["avg_response_time"] = (
            (daily_stats["avg_response_time"] * (daily_stats["queries"] - 1) + response_time)
            / daily_stats["queries"]
        )
    except Exception as e:
        logger.error(f"Error updating metrics: {str(e)}", exc_info=True)

def generate_response(message, conversation_history=None):
    """Generate chatbot response with comprehensive error handling"""
    start_time = datetime.now()
    success = False
    
    try:
        if not message.strip():
            logger.warning("Empty message received in generate_response")
            return "Por favor, escribe tu pregunta para poder ayudarte."
            
        response = get_chat_response(message, conversation_history)
        success = True
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_response: {str(e)}", exc_info=True)
        metrics["error_types"][type(e).__name__] = metrics["error_types"].get(type(e).__name__, 0) + 1
        return "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo más tarde."
    
    finally:
        update_metrics(start_time, success)
