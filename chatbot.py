import os
import openai
from datetime import datetime, timedelta
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from dotenv import load_dotenv
import re
import json
import locale

# Set locale for Spanish date formatting
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES')
    except:
        logging.warning("Spanish locale not available, falling back to default")

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')
if not openai.api_key:
    logger.error("OpenAI API key not found in environment variables")
    raise ValueError("OpenAI API key is required")

# Booking states
BOOKING_STATES = {
    'INITIAL': 0,
    'COLLECTING_NAME': 1,
    'COLLECTING_EMAIL': 2,
    'COLLECTING_PHONE': 3,
    'SELECTING_SERVICE': 4,
    'SELECTING_DATE': 5,
    'SELECTING_TIME': 6,
    'CONFIRMATION': 7
}

# Available services
SERVICES = [
    "Inteligencia Artificial (hasta 6.000€)",
    "Ventas Digitales (hasta 6.000€)",
    "Estrategia y Rendimiento de Negocio (hasta 6.000€)"
]

class BookingSession:
    def __init__(self):
        self.state = 'INITIAL'
        self.data = {}
        self.total_steps = 7
        self.current_step = 0
        
    def get_progress(self):
        """Calculate and format progress percentage"""
        if self.state == 'INITIAL':
            return ""
        progress = (BOOKING_STATES[self.state] / self.total_steps) * 100
        return f"\n\nProgreso: {progress:.0f}% completado"
    
    def format_state_data(self):
        """Format state data for storage in conversation"""
        return f"__STATE__{self.state}__DATA__{json.dumps(self.data)}__END__"
    
    @staticmethod
    def extract_state_data(message):
        """Extract state and data from conversation message"""
        if '__STATE__' not in message:
            return None, None
        try:
            state = message.split('__STATE__')[1].split('__DATA__')[0]
            data_str = message.split('__DATA__')[1].split('__END__')[0]
            return state, json.loads(data_str)
        except:
            return None, None

def validate_input(input_type, value):
    """Validate user input based on type"""
    validations = {
        'name': lambda x: bool(re.match("^[A-Za-zÀ-ÿ\s]{2,100}$", x)),
        'email': lambda x: bool(re.match(r"[^@]+@[^@]+\.[^@]+", x)),
        'phone': lambda x: not x or bool(re.match(r"^(?:\+34|0034|34)?[6789]\d{8}$", x)),
        'service_index': lambda x: x.isdigit() and 0 <= int(x)-1 < len(SERVICES),
        'date_index': lambda x: x.isdigit(),
        'time_index': lambda x: x.isdigit(),
        'confirmation': lambda x: x.lower() in ['si', 'sí', 'yes', 'no', 'cancel', 'cancelar']
    }
    return validations.get(input_type, lambda x: True)(value)

def format_date_spanish(date_str):
    """Format date in Spanish"""
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%-d de %B de %Y').lower()
    except:
        return date_str

def get_available_slots():
    """Get available appointment slots"""
    slots = []
    current_date = datetime.now()
    
    # Get next 7 available weekdays
    for i in range(14):  # Look ahead 14 days to find 7 available slots
        check_date = current_date + timedelta(days=i)
        if check_date.weekday() < 5:  # Monday = 0, Friday = 4
            # Get booked appointments
            booked_times = set(
                apt.time for apt in Appointment.query.filter_by(
                    date=check_date.date()
                ).all()
            )
            
            # Available time slots
            available_times = []
            start_time = datetime.strptime("10:30", "%H:%M")
            end_time = datetime.strptime("14:00", "%H:%M")
            current_time = start_time
            
            while current_time <= end_time:
                time_str = current_time.strftime("%H:%M")
                if time_str not in booked_times:
                    available_times.append(time_str)
                current_time += timedelta(minutes=30)
            
            if available_times:
                slots.append({
                    'date': check_date.strftime("%Y-%m-%d"),
                    'formatted_date': format_date_spanish(check_date.strftime("%Y-%m-%d")),
                    'times': available_times
                })
                
            if len(slots) >= 7:
                break
                
    return slots

def handle_booking_step(user_input, session):
    """Handle each step of the booking process"""
    
    error_messages = {
        'name': "Por favor, ingresa un nombre válido usando solo letras (ejemplo: Juan Pérez).",
        'email': "Por favor, ingresa un correo electrónico válido (ejemplo: nombre@dominio.com).",
        'phone': "Por favor, ingresa un número de teléfono español válido o escribe 'saltar'.",
        'service_index': "Por favor, selecciona un número válido de la lista de servicios.",
        'date_index': "Por favor, selecciona un número válido de la lista de fechas.",
        'time_index': "Por favor, selecciona un número válido de la lista de horarios.",
        'confirmation': "Por favor, responde 'sí' para confirmar o 'no' para cancelar."
    }
    
    if session.state == 'INITIAL':
        session.state = 'COLLECTING_NAME'
        return (
            "¡Perfecto! Para ayudarte a agendar una cita, necesito algunos datos. "
            "Por favor, introduce tu nombre completo." + 
            session.get_progress() +
            session.format_state_data()
        )
    
    elif session.state == 'COLLECTING_NAME':
        if not validate_input('name', user_input):
            return error_messages['name'] + session.get_progress() + session.format_state_data()
        
        session.data['name'] = user_input
        session.state = 'COLLECTING_EMAIL'
        return (
            f"Gracias {user_input}. Ahora necesito tu correo electrónico para enviarte "
            "la confirmación de la cita." + 
            session.get_progress() + 
            session.format_state_data()
        )
    
    elif session.state == 'COLLECTING_EMAIL':
        if not validate_input('email', user_input):
            return error_messages['email'] + session.get_progress() + session.format_state_data()
        
        session.data['email'] = user_input
        session.state = 'COLLECTING_PHONE'
        return (
            "Perfecto. ¿Podrías proporcionarme un número de teléfono para contactarte en caso necesario? "
            "(Este campo es opcional, puedes escribir 'saltar' para continuar)." + 
            session.get_progress() + 
            session.format_state_data()
        )
    
    elif session.state == 'COLLECTING_PHONE':
        if user_input.lower() == 'saltar':
            user_input = ''
            
        if not validate_input('phone', user_input):
            return error_messages['phone'] + session.get_progress() + session.format_state_data()
        
        session.data['phone'] = user_input
        session.state = 'SELECTING_SERVICE'
        
        services_text = "\n".join(
            f"{i+1}. {service}"
            for i, service in enumerate(SERVICES)
        )
        
        return (
            "Gracias. ¿Qué servicio te interesa?\n\n" +
            services_text + "\n\n"
            "Por favor, selecciona el número del servicio deseado." + 
            session.get_progress() + 
            session.format_state_data()
        )
    
    elif session.state == 'SELECTING_SERVICE':
        if not validate_input('service_index', user_input):
            return error_messages['service_index'] + session.get_progress() + session.format_state_data()
        
        service_index = int(user_input) - 1
        session.data['service'] = SERVICES[service_index]
        session.state = 'SELECTING_DATE'
        
        slots = get_available_slots()
        if not slots:
            return (
                "Lo siento, no hay fechas disponibles en los próximos días. "
                "Por favor, intenta más tarde." + 
                session.format_state_data()
            )
        
        dates_text = "\n".join(
            f"{i+1}. {slot['formatted_date']}"
            for i, slot in enumerate(slots)
        )
        
        return (
            f"Has seleccionado: {session.data['service']}\n\n"
            f"Estas son las fechas disponibles:\n\n{dates_text}\n\n"
            "Por favor, selecciona el número de la fecha que prefieres." + 
            session.get_progress() + 
            session.format_state_data()
        )
    
    elif session.state == 'SELECTING_DATE':
        if not validate_input('date_index', user_input):
            return error_messages['date_index'] + session.get_progress() + session.format_state_data()
        
        slots = get_available_slots()
        date_index = int(user_input) - 1
        
        if date_index < 0 or date_index >= len(slots):
            return error_messages['date_index'] + session.get_progress() + session.format_state_data()
        
        selected_date = slots[date_index]
        session.data['date'] = selected_date['date']
        session.data['formatted_date'] = selected_date['formatted_date']
        session.state = 'SELECTING_TIME'
        
        times_text = "\n".join(
            f"{i+1}. {time}"
            for i, time in enumerate(selected_date['times'])
        )
        
        return (
            f"Has seleccionado el {selected_date['formatted_date']}.\n\n"
            f"Estos son los horarios disponibles:\n\n{times_text}\n\n"
            "Por favor, selecciona el número del horario que prefieres." + 
            session.get_progress() + 
            session.format_state_data()
        )
    
    elif session.state == 'SELECTING_TIME':
        if not validate_input('time_index', user_input):
            return error_messages['time_index'] + session.get_progress() + session.format_state_data()
        
        slots = get_available_slots()
        selected_slot = next(
            slot for slot in slots 
            if slot['date'] == session.data['date']
        )
        
        time_index = int(user_input) - 1
        if time_index < 0 or time_index >= len(selected_slot['times']):
            return error_messages['time_index'] + session.get_progress() + session.format_state_data()
        
        session.data['time'] = selected_slot['times'][time_index]
        session.state = 'CONFIRMATION'
        
        phone_info = (
            f"Teléfono: {session.data['phone']}\n"
            if session.data.get('phone')
            else "Teléfono: No proporcionado\n"
        )
        
        return (
            "Por favor, revisa los detalles de tu cita:\n\n"
            f"Nombre: {session.data['name']}\n"
            f"Email: {session.data['email']}\n" +
            phone_info +
            f"Fecha: {session.data['formatted_date']}\n"
            f"Hora: {session.data['time']}\n"
            f"Servicio: {session.data['service']}\n\n"
            "¿Confirmas esta cita? (Responde 'sí' para confirmar o 'no' para cancelar)" + 
            session.get_progress() + 
            session.format_state_data()
        )
    
    elif session.state == 'CONFIRMATION':
        if not validate_input('confirmation', user_input):
            return error_messages['confirmation'] + session.get_progress() + session.format_state_data()
        
        if user_input.lower() in ['si', 'sí', 'yes']:
            try:
                # Create appointment
                appointment = Appointment(
                    name=session.data['name'],
                    email=session.data['email'],
                    date=datetime.strptime(session.data['date'], '%Y-%m-%d').date(),
                    time=session.data['time'],
                    service=session.data['service']
                )
                db.session.add(appointment)
                db.session.commit()
                
                # Send confirmation emails
                send_appointment_confirmation(appointment)
                schedule_reminder_email(appointment)
                
                return (
                    "¡Tu cita ha sido confirmada! Te hemos enviado un correo electrónico "
                    "con los detalles. ¿Hay algo más en lo que pueda ayudarte?" +
                    "\n\nBOOKING_COMPLETE" +
                    session.format_state_data()
                )
            except Exception as e:
                logger.error(f"Error creating appointment: {str(e)}")
                return (
                    "Lo siento, ha ocurrido un error al procesar tu cita. "
                    "Por favor, intenta de nuevo más tarde." +
                    session.format_state_data()
                )
        else:
            return (
                "De acuerdo, he cancelado la reserva. "
                "¿Hay algo más en lo que pueda ayudarte?" +
                "\n\nBOOKING_CANCELLED" +
                session.format_state_data()
            )
    
    return (
        "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo." +
        session.format_state_data()
    )

def generate_response(user_message, conversation_history=None):
    """Generate chatbot response"""
    try:
        if not user_message.strip():
            return "Por favor, escribe tu pregunta para poder ayudarte."

        if conversation_history is None:
            conversation_history = []

        # Extract state data from last bot message
        current_state = 'INITIAL'
        booking_data = {}
        
        for msg in conversation_history:
            if not msg.get('is_user', True):
                state, data = BookingSession.extract_state_data(msg['text'])
                if state:
                    current_state = state
                    booking_data = data or {}

        # Check if we're in booking flow or user wants to book
        if current_state != 'INITIAL' or 'cita' in user_message.lower():
            session = BookingSession()
            session.state = current_state
            session.data = booking_data
            return handle_booking_step(user_message, session)

        # Regular chatbot response using OpenAI
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres el asistente virtual de KIT CONSULTING, especializado en ayudas "
                    "gubernamentales para la transformación digital de empresas. "
                    "Tu objetivo es explicar el programa y guiar a los usuarios en el proceso. "
                    "Si detectas interés, especialmente en servicios de IA, "
                    "sugiere agendar una cita de consultoría."
                )
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            content = msg['text']
            if not msg.get('is_user', True) and '__STATE__' in content:
                content = content.split('__STATE__')[0]
            messages.append({
                "role": "user" if msg.get('is_user', True) else "assistant",
                "content": content
            })

        messages.append({"role": "user", "content": user_message})

        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        return completion.choices[0].message.content

    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo más tarde."
