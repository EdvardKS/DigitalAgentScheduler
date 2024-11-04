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
    'SELECTING_SERVICE': 3,
    'SELECTING_DATE': 4,
    'SELECTING_TIME': 5,
    'CONFIRMING': 6
}

class AppointmentSession:
    def __init__(self):
        self.state = APPOINTMENT_STATES['IDLE']
        self.data = {
            'name': None,
            'email': None,
            'service': None,
            'date': None,
            'time': None
        }
        self.available_dates = []
        self.available_times = []

# Conversation session storage
appointment_sessions = {}

def format_date(date_str):
    """Format date in a more readable way"""
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    return date_obj.strftime("%d de %B de %Y")

def format_time(time_str):
    """Format time in 24-hour format"""
    return time_str

def get_chat_response(user_message, conversation_history=None):
    """Generate a response using OpenAI's ChatGPT with appointment booking logic"""
    try:
        logger.info(f"Processing chat request - Message length: {len(user_message)}")
        
        if not user_message.strip():
            logger.warning("Empty message received")
            return "Por favor, escribe tu pregunta para poder ayudarte."

        # Initialize session if not exists
        session_id = "default"  # In production, use actual session ID
        if session_id not in appointment_sessions and any(keyword in user_message.lower() for keyword in ["cita", "appointment", "reservar", "agendar"]):
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
                "content": f"""Eres el asistente virtual de KIT CONSULTING, especializado en servicios de consultoría en IA. 
                Si el usuario menciona que quiere agendar una cita o consultoría, inicia el proceso de reserva.
                Información del programa: {COMPANY_INFO}"""
            }
        ]

        # Add conversation history
        if conversation_history:
            for msg in conversation_history:
                messages.append({
                    "role": "user" if msg["is_user"] else "assistant",
                    "content": msg["text"]
                })

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
    """Handle the step-by-step appointment booking process with enhanced validation"""
    try:
        if session.state == APPOINTMENT_STATES['COLLECTING_NAME']:
            is_valid, error_msg = AppointmentManager.validate_name(message)
            if is_valid:
                session.data['name'] = message
                session.state = APPOINTMENT_STATES['COLLECTING_EMAIL']
                return "Gracias por proporcionar tu nombre. Por favor, introduce tu correo electrónico para enviarte la confirmación:"
            return f"Lo siento, el nombre proporcionado no es válido: {error_msg}. Por favor, introduce tu nombre completo:"

        elif session.state == APPOINTMENT_STATES['COLLECTING_EMAIL']:
            is_valid, error_msg = AppointmentManager.validate_email(message)
            if is_valid:
                session.data['email'] = message
                session.state = APPOINTMENT_STATES['SELECTING_SERVICE']
                return """¿Qué tipo de servicio te interesa?
                
1. Consultoría en Inteligencia Artificial
2. Ventas Digitales
3. Estrategia y Rendimiento de Negocio

Por favor, selecciona el número del servicio deseado:"""
            return f"El correo electrónico no es válido: {error_msg}. Por favor, introduce un correo electrónico válido:"

        elif session.state == APPOINTMENT_STATES['SELECTING_SERVICE']:
            service_map = {
                "1": "AI Consulting",
                "2": "Digital Sales",
                "3": "Business Strategy"
            }
            selected_service = service_map.get(message.strip())
            if selected_service:
                session.data['service'] = selected_service
                session.state = APPOINTMENT_STATES['SELECTING_DATE']
                # Get next 7 available weekdays
                available_dates = []
                current_date = datetime.now().date()
                days_ahead = 0
                while len(available_dates) < 7:
                    check_date = current_date + timedelta(days=days_ahead)
                    if check_date.weekday() < 5:  # Monday to Friday
                        available_dates.append(check_date.strftime("%Y-%m-%d"))
                    days_ahead += 1
                session.available_dates = available_dates
                dates_display = "\n".join([f"{i+1}. {format_date(date)}" for i, date in enumerate(available_dates)])
                return f"""Por favor, selecciona una fecha disponible (indica el número):

{dates_display}"""
            return "Por favor, selecciona un número válido (1, 2 o 3) para el servicio deseado:"

        elif session.state == APPOINTMENT_STATES['SELECTING_DATE']:
            try:
                selection = int(message.strip()) - 1
                if 0 <= selection < len(session.available_dates):
                    selected_date = session.available_dates[selection]
                    session.data['date'] = selected_date
                    available_slots = AppointmentManager.get_available_slots(selected_date)
                    if not available_slots:
                        return "Lo siento, no hay horarios disponibles para esta fecha. Por favor, selecciona otra fecha:"
                    session.available_times = available_slots
                    session.state = APPOINTMENT_STATES['SELECTING_TIME']
                    times_display = "\n".join([f"{i+1}. {format_time(time)}" for i, time in enumerate(available_slots)])
                    return f"""Horarios disponibles para el {format_date(selected_date)} (indica el número):

{times_display}"""
                return f"Por favor, selecciona un número válido entre 1 y {len(session.available_dates)}:"
            except ValueError:
                return "Por favor, introduce un número válido para seleccionar la fecha:"

        elif session.state == APPOINTMENT_STATES['SELECTING_TIME']:
            try:
                selection = int(message.strip()) - 1
                if 0 <= selection < len(session.available_times):
                    selected_time = session.available_times[selection]
                    session.data['time'] = selected_time
                    session.state = APPOINTMENT_STATES['CONFIRMING']
                    return f"""Por favor, confirma los detalles de tu cita:

📅 Fecha: {format_date(session.data['date'])}
⏰ Hora: {format_time(session.data['time'])}
👤 Nombre: {session.data['name']}
📧 Email: {session.data['email']}
💼 Servicio: {session.data['service']}

¿Deseas confirmar esta cita? (Responde 'Sí' o 'No')"""
                return f"Por favor, selecciona un número válido entre 1 y {len(session.available_times)}:"
            except ValueError:
                return "Por favor, introduce un número válido para seleccionar el horario:"

        elif session.state == APPOINTMENT_STATES['CONFIRMING']:
            if message.lower() in ['si', 'sí', 'yes', 's', 'y']:
                success, message, appointment = AppointmentManager.create_appointment(session.data)
                if success:
                    appointment_sessions.pop("default")
                    return """¡Tu cita ha sido confirmada! 
                    
Te hemos enviado un correo electrónico con los detalles de la cita y las instrucciones. ¿Hay algo más en lo que pueda ayudarte?"""
                return f"Lo siento, ha ocurrido un error al crear la cita: {message}. Por favor, intenta de nuevo más tarde."
            elif message.lower() in ['no', 'n']:
                appointment_sessions.pop("default")
                return "Cita cancelada. ¿Hay algo más en lo que pueda ayudarte?"
            return "Por favor, responde 'Sí' o 'No' para confirmar la cita."

        elif any(keyword in message.lower() for keyword in ["cita", "appointment", "reservar", "agendar"]):
            session.state = APPOINTMENT_STATES['COLLECTING_NAME']
            return """¡Con gusto te ayudo a agendar una cita! Para comenzar, por favor proporciona tu nombre completo:"""

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

# Company information
COMPANY_INFO = """
KIT CONSULTING es un programa especializado en asesoría digital y transformación tecnológica. Ofrecemos servicios de consultoría en:

1. Inteligencia Artificial (hasta 6.000€)
- Implementación de soluciones IA
- Automatización de procesos
- Análisis predictivo

2. Ventas Digitales (hasta 6.000€)
- Estrategias de e-commerce
- Marketing digital
- Optimización de conversión

3. Estrategia de Negocio (hasta 6.000€)
- Transformación digital
- Análisis de rendimiento
- Optimización de procesos

Beneficios por segmento:
- Pequeñas empresas (10-49 empleados): 12.000€
- Medianas empresas (50-99 empleados): 18.000€
- Grandes PYMEs (100-249 empleados): 24.000€

Horario de atención:
- Lunes a Viernes
- 10:30 AM a 2:00 PM

Para más información:
- Email: info@navegatel.org
- Teléfono: 673 66 09 10
"""

def update_metrics(start_time, success):
    """Update chatbot performance metrics"""
    end_time = datetime.now()
    response_time = (end_time - start_time).total_seconds() * 1000
    
    metrics["total_queries"] += 1
    if success:
        metrics["successful_queries"] += 1
    else:
        metrics["failed_queries"] += 1
    
    metrics["response_times"].append(response_time)
    
    # Update daily stats
    today = end_time.date().isoformat()
    if today not in metrics["daily_stats"]:
        metrics["daily_stats"][today] = {"total": 0, "successful": 0}
    metrics["daily_stats"][today]["total"] += 1
    if success:
        metrics["daily_stats"][today]["successful"] += 1

# Initialize metrics
metrics = {
    "total_queries": 0,
    "successful_queries": 0,
    "failed_queries": 0,
    "response_times": [],
    "daily_stats": {},
    "error_types": {}
}
