import os
import openai
from datetime import datetime, timedelta
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from appointment_manager import AppointmentManager
from dotenv import load_dotenv
import re

# Load environment variables
load_dotenv()

# Spanish translations for dates
SPANISH_DAYS = {
    'Monday': 'Lunes',
    'Tuesday': 'Martes',
    'Wednesday': 'Miércoles',
    'Thursday': 'Jueves',
    'Friday': 'Viernes',
    'Saturday': 'Sábado',
    'Sunday': 'Domingo'
}

SPANISH_MONTHS = {
    'January': 'enero',
    'February': 'febrero',
    'March': 'marzo',
    'April': 'abril',
    'May': 'mayo',
    'June': 'junio',
    'July': 'julio',
    'August': 'agosto',
    'September': 'septiembre',
    'October': 'octubre',
    'November': 'noviembre',
    'December': 'diciembre'
}

def format_date_spanish(date_obj):
    """Format a date in Spanish"""
    eng_day = date_obj.strftime('%A')
    eng_month = date_obj.strftime('%B')
    day = SPANISH_DAYS[eng_day]
    month = SPANISH_MONTHS[eng_month]
    return f"{day}, {date_obj.day} de {month}"

def format_date_full_spanish(date_obj):
    """Format a full date in Spanish including year"""
    eng_day = date_obj.strftime('%A')
    eng_month = date_obj.strftime('%B')
    day = SPANISH_DAYS[eng_day]
    month = SPANISH_MONTHS[eng_month]
    return f"{day}, {date_obj.day} de {month} de {date_obj.year}"

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
    
MODELO_FINETUNED = os.getenv('MODELO_FINETUNED')

# Metrics tracking
metrics = {
    "total_queries": 0,
    "successful_queries": 0,
    "failed_queries": 0,
    "response_times": [],
    "daily_stats": {},
    "error_types": {}
}

# Appointment conversation states
APPOINTMENT_STATES = {
    'INIT': 'init',
    'GET_NAME': 'get_name',
    'GET_EMAIL': 'get_email',
    'CONFIRM_EMAIL': 'confirm_email',
    'GET_SERVICE': 'get_service',
    'GET_DATE': 'get_date',
    'GET_TIME': 'get_time',
    'CONFIRM': 'confirm'
}

# Validation patterns
EMAIL_PATTERN = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
NAME_MIN_LENGTH = 2
NAME_MAX_LENGTH = 50

# Available services
AVAILABLE_SERVICES = {
    '1': 'Inteligencia Artificial',
    '2': 'Ventas Digitales',
    '3': 'Estrategia y Rendimiento de Negocio'
}

class AppointmentData:
    def __init__(self):
        self.name = None
        self.email = None
        self.service = None
        self.date = None
        self.time = None
        self.state = APPOINTMENT_STATES['INIT']
        self.temp_email = None
        self.available_dates = []
        self.available_times = []

    def is_complete(self):
        return all([self.name, self.email, self.service, self.date, self.time])

    def to_dict(self):
        return {
            'name': self.name,
            'email': self.email,
            'service': self.service,
            'date': self.date,
            'time': self.time
        }

def validate_name(name):
    """Validate the name input"""
    if not name or not isinstance(name, str):
        return False, "Por favor, proporciona un nombre válido."
    
    name = name.strip()
    if len(name) < NAME_MIN_LENGTH or len(name) > NAME_MAX_LENGTH:
        return False, f"El nombre debe tener entre {NAME_MIN_LENGTH} y {NAME_MAX_LENGTH} caracteres."
    
    if not all(c.isalpha() or c.isspace() for c in name):
        return False, "El nombre solo puede contener letras y espacios."
        
    return True, name

def validate_email(email):
    """Validate the email format"""
    if not email or not isinstance(email, str):
        return False, "Por favor, proporciona un email válido."
    
    email = email.strip().lower()
    if not re.match(EMAIL_PATTERN, email):
        return False, "Por favor, proporciona un email válido."
        
    return True, email

def get_available_dates():
    """Get available dates for the next 7 days excluding weekends"""
    dates = []
    current_date = datetime.now().date()
    days_ahead = 0
    
    while len(dates) < 7:
        check_date = current_date + timedelta(days=days_ahead)
        if check_date.weekday() < 5:  # Monday = 0, Friday = 4
            dates.append({
                'date': check_date.strftime('%Y-%m-%d'),
                'display': format_date_spanish(check_date)
            })
        days_ahead += 1
        
    return dates

def format_appointment_summary(data):
    """Format appointment data for confirmation message"""
    date_obj = datetime.strptime(data.date, '%Y-%m-%d')
    formatted_date = format_date_full_spanish(date_obj)
    
    return f"""Por favor, confirma los detalles de tu cita:

📅 Fecha: {formatted_date}
🕒 Hora: {data.time}
👤 Nombre: {data.name}
📧 Email: {data.email}
💼 Servicio: {data.service}

¿Deseas confirmar esta cita? (Responde 'sí' para confirmar o 'no' para cancelar)"""

def handle_appointment_conversation(message, appointment_data):
    """Handle the appointment booking conversation flow"""
    try:
        message = message.strip().lower()
        
        if appointment_data.state == APPOINTMENT_STATES['INIT']:
            appointment_data.state = APPOINTMENT_STATES['GET_NAME']
            return "¡Perfecto! Para programar tu cita, primero necesito algunos datos. Por favor, dime tu nombre completo."
            
        elif appointment_data.state == APPOINTMENT_STATES['GET_NAME']:
            is_valid, result = validate_name(message)
            if is_valid:
                appointment_data.name = result
                appointment_data.state = APPOINTMENT_STATES['GET_EMAIL']
                return f"Gracias {result}. Ahora, por favor proporciona tu dirección de email para enviarte la confirmación."
            return result
            
        elif appointment_data.state == APPOINTMENT_STATES['GET_EMAIL']:
            is_valid, result = validate_email(message)
            if is_valid:
                appointment_data.temp_email = result
                appointment_data.state = APPOINTMENT_STATES['CONFIRM_EMAIL']
                return f"Para confirmar, ¿es {result} tu dirección de email correcta? (responde 'sí' o 'no')"
            return result
            
        elif appointment_data.state == APPOINTMENT_STATES['CONFIRM_EMAIL']:
            if message in ['si', 'sí']:
                appointment_data.email = appointment_data.temp_email
                appointment_data.state = APPOINTMENT_STATES['GET_SERVICE']
                service_options = "\n".join([f"{key}. {value}" for key, value in AVAILABLE_SERVICES.items()])
                return f"""¿Qué servicio te interesa?

{service_options}

Por favor, selecciona el número del servicio."""
            elif message == 'no':
                appointment_data.state = APPOINTMENT_STATES['GET_EMAIL']
                return "Por favor, proporciona tu dirección de email correcta."
            return "Por favor, responde 'sí' o 'no'."
            
        elif appointment_data.state == APPOINTMENT_STATES['GET_SERVICE']:
            service = AVAILABLE_SERVICES.get(message)
            if not service:
                service_options = "\n".join([f"{key}. {value}" for key, value in AVAILABLE_SERVICES.items()])
                return f"Por favor, selecciona un número válido del servicio:\n\n{service_options}"
                
            appointment_data.service = service
            appointment_data.state = APPOINTMENT_STATES['GET_DATE']
            
            available_dates = get_available_dates()
            appointment_data.available_dates = available_dates
            date_options = "\n".join([f"{i+1}. {date['display']}" for i, date in enumerate(available_dates)])
            
            return f"""Estas son las fechas disponibles para los próximos días laborables:

{date_options}

Por favor, selecciona el número de la fecha que prefieras."""
            
        elif appointment_data.state == APPOINTMENT_STATES['GET_DATE']:
            try:
                date_index = int(message) - 1
                if 0 <= date_index < len(appointment_data.available_dates):
                    selected_date = appointment_data.available_dates[date_index]['date']
                    appointment_data.date = selected_date
                    appointment_data.state = APPOINTMENT_STATES['GET_TIME']
                    
                    available_slots = AppointmentManager.get_available_slots(selected_date)
                    if not available_slots:
                        appointment_data.state = APPOINTMENT_STATES['GET_DATE']
                        return "Lo siento, no hay horarios disponibles para esta fecha. Por favor, selecciona otra fecha."
                    
                    appointment_data.available_times = available_slots
                    time_options = "\n".join([f"{i+1}. {slot}" for i, slot in enumerate(available_slots)])
                    
                    return f"""Horarios disponibles para la fecha seleccionada:

{time_options}

Por favor, selecciona el número del horario que prefieras."""
                else:
                    date_options = "\n".join([f"{i+1}. {date['display']}" for i, date in enumerate(appointment_data.available_dates)])
                    return f"Por favor, selecciona un número válido de la lista:\n\n{date_options}"
            except ValueError:
                return "Por favor, ingresa un número válido."
                
        elif appointment_data.state == APPOINTMENT_STATES['GET_TIME']:
            try:
                time_index = int(message) - 1
                if 0 <= time_index < len(appointment_data.available_times):
                    appointment_data.time = appointment_data.available_times[time_index]
                    appointment_data.state = APPOINTMENT_STATES['CONFIRM']
                    return format_appointment_summary(appointment_data)
                else:
                    time_options = "\n".join([f"{i+1}. {slot}" for i, slot in enumerate(appointment_data.available_times)])
                    return f"Por favor, selecciona un número válido del horario:\n\n{time_options}"
            except ValueError:
                return "Por favor, ingresa un número válido."
                
        elif appointment_data.state == APPOINTMENT_STATES['CONFIRM']:
            if message in ['si', 'sí']:
                try:
                    appointment = AppointmentManager.create_appointment(**appointment_data.to_dict())
                    return """¡Perfecto! Tu cita ha sido confirmada. En breve recibirás un email con todos los detalles.

¿Hay algo más en lo que pueda ayudarte?"""
                except Exception as e:
                    logger.error(f"Error creating appointment: {str(e)}")
                    return "Lo siento, ha ocurrido un error al crear la cita. Por favor, inténtalo de nuevo más tarde."
            elif message == 'no':
                appointment_data.state = APPOINTMENT_STATES['INIT']
                return "Entiendo. ¿Quieres intentar programar una nueva cita?"
            return "Por favor, responde 'sí' para confirmar o 'no' para cancelar."
            
    except Exception as e:
        logger.error(f"Error in appointment conversation: {str(e)}")
        return "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo."

def get_chat_response(user_message, conversation_history=None):
    """Generate a response using OpenAI's ChatGPT with enhanced error handling"""
    try:
        logger.info(f"Processing chat request - Message length: {len(user_message)}")
        
        if not user_message.strip():
            logger.warning("Empty message received")
            return "Por favor, escribe tu pregunta para poder ayudarte."

        if conversation_history is None:
            conversation_history = []

        # Check if we're in an appointment booking flow
        appointment_data = None
        for msg in conversation_history:
            if not msg.get('is_user') and 'appointment_data' in msg:
                appointment_data = msg['appointment_data']
                break

        if appointment_data and appointment_data.state != APPOINTMENT_STATES['INIT']:
            return handle_appointment_conversation(user_message, appointment_data)

        if any(word in user_message.lower() for word in ['cita', 'agendar', 'reservar', 'consulta']):
            appointment_data = AppointmentData()
            conversation_history.append({
                'is_user': False,
                'appointment_data': appointment_data
            })
            return handle_appointment_conversation("", appointment_data)

        # Regular chatbot conversation
        messages = [
            {
                "role": "system",
                "content": """Eres el asistente virtual de Navegatel, especializado en el programa KIT CONSULTING. 
Tu objetivo es ayudar a los usuarios a entender el programa de ayudas y guiarlos en el proceso de solicitud.
Si el usuario muestra interés en agendar una cita, pregúntale si desea programar una consulta."""
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            if 'appointment_data' not in msg:
                messages.append({
                    "role": "user" if msg["is_user"] else "assistant",
                    "content": msg["text"]
                })

        # Add the current message
        messages.append({"role": "user", "content": user_message})

        try:
            response = openai.ChatCompletion.create(
                model=MODELO_FINETUNED,
                messages=messages,
                max_tokens=500,
                temperature=0.7,
                top_p=0.9,
                presence_penalty=0.6,
                frequency_penalty=0.3,
                request_timeout=30
            )
            logger.info("Successfully received response from OpenAI")
            return response.choices[0].message["content"]

        except openai.error.Timeout:
            logger.error("OpenAI API request timed out")
            return "Lo siento, la respuesta está tardando más de lo esperado. Por favor, intenta de nuevo."
        
        except openai.error.APIError as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo en unos momentos."
        
        except openai.error.RateLimitError:
            logger.error("OpenAI API rate limit exceeded")
            return "Estamos experimentando un alto volumen de consultas. Por favor, intenta de nuevo en unos minutos."

    except Exception as e:
        logger.error(f"Unexpected error in get_chat_response: {str(e)}", exc_info=True)
        metrics["error_types"][type(e).__name__] = metrics["error_types"].get(type(e).__name__, 0) + 1
        return "Lo siento, ha ocurrido un error inesperado. Por favor, intenta de nuevo."

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
        return "Lo siento, ha ocurrido un error inesperado. Por favor, intenta de nuevo."
    
    finally:
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
