import os
import openai
from datetime import datetime, timedelta
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from appointments import AppointmentManager
from dotenv import load_dotenv

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

# Appointment booking states
APPOINTMENT_STATES = {
    'IDLE': 0,
    'COLLECTING_NAME': 1,
    'COLLECTING_EMAIL': 2,
    'SELECTING_DATE': 3,
    'SELECTING_TIME': 4,
    'CONFIRMING': 5
}

# Conversation session storage
appointment_sessions = {}

class AppointmentSession:
    def __init__(self):
        self.state = APPOINTMENT_STATES['IDLE']
        self.data = {
            'name': None,
            'email': None,
            'date': None,
            'time': None,
            'service': 'AI Consulting'  # Default service
        }

def get_chat_response(user_message, conversation_history=None):
    """Generate a response using OpenAI's ChatGPT with appointment booking logic"""
    try:
        logger.info(f"Processing chat request - Message length: {len(user_message)}")
        
        if not user_message.strip():
            logger.warning("Empty message received")
            return "Por favor, escribe tu pregunta para poder ayudarte."

        # Initialize session if not exists
        session_id = "default"  # In production, use actual session ID
        if session_id not in appointment_sessions and ("cita" in user_message.lower() or "appointment" in user_message.lower()):
            appointment_sessions[session_id] = AppointmentSession()

        # Handle appointment booking flow
        if session_id in appointment_sessions:
            session = appointment_sessions[session_id]
            response = handle_appointment_flow(user_message, session)
            if response:
                return response

        # Prepare the conversation with system context
        messages = [
            {
                "role": "system",
                "content": f"""Eres el asistente virtual de Navegatel, especializado en el programa KIT CONSULTING. 
                Si el usuario menciona que quiere agendar una cita o consultoría, inicia el proceso de reserva preguntando su nombre.
                Información del programa: {COMPANY_INFO}"""
            }
        ]

        # Add conversation history
        if conversation_history:
            for msg in conversation_history:
                messages.append({"role": "user" if msg["is_user"] else "assistant", "content": msg["text"]})

        # Add the current message
        messages.append({"role": "user", "content": user_message})

        # Get response from OpenAI
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
            top_p=0.9
        )
        logger.info("Successfully received response from OpenAI")
        return response.choices[0].message["content"]

    except Exception as e:
        logger.error(f"Error in get_chat_response: {str(e)}", exc_info=True)
        return "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo."

def handle_appointment_flow(message, session):
    """Handle the step-by-step appointment booking process"""
    try:
        if session.state == APPOINTMENT_STATES['COLLECTING_NAME']:
            is_valid, error_msg = AppointmentManager.validate_name(message)
            if is_valid:
                session.data['name'] = message
                session.state = APPOINTMENT_STATES['COLLECTING_EMAIL']
                return "Gracias. Ahora, por favor proporciona tu correo electrónico para las confirmaciones:"
            return f"El nombre no es válido: {error_msg}. Por favor, intenta de nuevo:"

        elif session.state == APPOINTMENT_STATES['COLLECTING_EMAIL']:
            is_valid, error_msg = AppointmentManager.validate_email(message)
            if is_valid:
                session.data['email'] = message
                session.state = APPOINTMENT_STATES['SELECTING_DATE']
                # Show available dates for next 7 days
                available_dates = get_available_dates()
                return f"Gracias. Estas son las fechas disponibles en los próximos 7 días:\n{available_dates}\nPor favor, selecciona una fecha (YYYY-MM-DD):"
            return f"El correo electrónico no es válido: {error_msg}. Por favor, intenta de nuevo:"

        elif session.state == APPOINTMENT_STATES['SELECTING_DATE']:
            is_valid, error_msg = AppointmentManager.validate_date(message)
            if is_valid:
                session.data['date'] = message
                available_slots = AppointmentManager.get_available_slots(message)
                if not available_slots:
                    return "No hay horarios disponibles para esta fecha. Por favor, selecciona otra fecha:"
                session.state = APPOINTMENT_STATES['SELECTING_TIME']
                slots_str = "\n".join(available_slots)
                return f"Horarios disponibles:\n{slots_str}\nPor favor, selecciona un horario (HH:MM):"
            return f"La fecha no es válida: {error_msg}. Por favor, intenta de nuevo:"

        elif session.state == APPOINTMENT_STATES['SELECTING_TIME']:
            is_valid, error_msg = AppointmentManager.validate_time(message)
            if is_valid:
                session.data['time'] = message
                session.state = APPOINTMENT_STATES['CONFIRMING']
                return f"""Por favor, confirma los detalles de tu cita:
                Nombre: {session.data['name']}
                Email: {session.data['email']}
                Fecha: {session.data['date']}
                Hora: {session.data['time']}
                Servicio: {session.data['service']}
                
                ¿Deseas confirmar esta cita? (Sí/No)"""
            return f"El horario no es válido: {error_msg}. Por favor, intenta de nuevo:"

        elif session.state == APPOINTMENT_STATES['CONFIRMING']:
            if message.lower() in ['si', 'sí', 'yes', 's', 'y']:
                success, message, appointment = AppointmentManager.create_appointment(session.data)
                if success:
                    # Clear session
                    appointment_sessions.pop("default")
                    return "¡Tu cita ha sido confirmada! Te hemos enviado un correo electrónico con los detalles."
                return f"Error al crear la cita: {message}. Por favor, intenta de nuevo más tarde."
            elif message.lower() in ['no', 'n']:
                # Clear session
                appointment_sessions.pop("default")
                return "Cita cancelada. ¿Hay algo más en lo que pueda ayudarte?"
            return "Por favor, responde 'Sí' o 'No' para confirmar la cita."

        elif "cita" in message.lower() or "appointment" in message.lower():
            session.state = APPOINTMENT_STATES['COLLECTING_NAME']
            return "Por favor, proporciona tu nombre completo:"

        return None

    except Exception as e:
        logger.error(f"Error in handle_appointment_flow: {str(e)}", exc_info=True)
        return "Lo siento, ha ocurrido un error en el proceso de reserva. Por favor, intenta de nuevo."

def get_available_dates():
    """Get available dates for the next 7 days"""
    dates = []
    current_date = datetime.now().date()
    for i in range(7):
        check_date = current_date + timedelta(days=i)
        if check_date.weekday() < 5:  # Monday to Friday
            dates.append(check_date.strftime("%Y-%m-%d"))
    return "\n".join(dates)

# Metrics tracking (unchanged)
metrics = {
    "total_queries": 0,
    "successful_queries": 0,
    "failed_queries": 0,
    "response_times": [],
    "daily_stats": {},
    "error_types": {}
}

# Company information (unchanged)
COMPANY_INFO = """
Somos Navegatel, una empresa especializada en asesoría digital, expertos en el programa KIT CONSULTING. El KIT CONSULTING es un programa de ayudas del Gobierno de España que permite a pymes diseñar la hoja de ruta para su transformación digital.

Servicios principales:
1. Inteligencia Artificial - hasta 6.000€
2. Ventas Digitales - hasta 6.000€
3. Estrategia y Rendimiento de Negocio - hasta 6.000€

Segmentos de empresas:
- Segmento A (10-49 empleados): 12.000€
- Segmento B (50-99 empleados): 18.000€
- Segmento C (100-249 empleados): 24.000€

Requisitos básicos:
- Tener domicilio fiscal en territorio español
- Ser pequeña o mediana empresa
- Estar inscrito en el censo de empresarios
- No tener consideración de empresa en crisis
- Estar al corriente de obligaciones tributarias

IMPORTANTE:
- Responde solo ha preguntas relacionadas con el KIT CONSULTING o servicios de Navegatel.
- Somos especialistas en Inteligencia Artificial, Ventas Digitales y Estrategia y Rendimiento de Negocio.
- Guía al usuario para que elija IA y que coja una cita utilizando este mismo CHATBOT.
- Para contacto directo: info@navegatel.org o 673 66 09 10
"""

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
        return "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo."
    
    finally:
        update_metrics(start_time, success)
