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

# Define conversation states
CONVERSATION_STATES = {
    'INITIAL': 'initial',
    'COLLECTING_NAME': 'collecting_name',
    'COLLECTING_EMAIL': 'collecting_email',
    'SELECTING_SERVICE': 'selecting_service',
    'SELECTING_DATE': 'selecting_date',
    'SELECTING_TIME': 'selecting_time',
    'CONFIRMATION': 'confirmation'
}

# Available services
SERVICES = [
    "Desarrollo de IA y Machine Learning",
    "Consultoría en Transformación Digital",
    "Implementación de Chatbots y Automatización",
    "Análisis de Datos y Business Intelligence"
]

class BookingSession:
    def __init__(self):
        self.state = CONVERSATION_STATES['INITIAL']
        self.data = {}
        self.total_steps = 5
        self.current_step = 0

    def update_state(self, new_state):
        self.state = new_state
        self.current_step = {
            CONVERSATION_STATES['INITIAL']: 0,
            CONVERSATION_STATES['COLLECTING_NAME']: 1,
            CONVERSATION_STATES['COLLECTING_EMAIL']: 2,
            CONVERSATION_STATES['SELECTING_SERVICE']: 3,
            CONVERSATION_STATES['SELECTING_DATE']: 4,
            CONVERSATION_STATES['SELECTING_TIME']: 5,
            CONVERSATION_STATES['CONFIRMATION']: 5
        }.get(new_state, 0)

    def get_progress(self):
        return f"\n\n📊 Progreso: {(self.current_step / self.total_steps * 100):.0f}% completado"

def validate_name(name):
    """Validate that name contains only letters and spaces"""
    return bool(re.match("^[A-Za-zÀ-ÿ\s]{2,50}$", name))

def validate_email(email):
    """Validate email format"""
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))

def get_available_slots(date=None):
    """Get available time slots for a specific date"""
    available_slots = []
    now = datetime.now()
    
    # If no date specified, get next 5 business days
    if not date:
        current_date = now
        days_ahead = 0
        while len(available_slots) < 5:
            check_date = current_date + timedelta(days=days_ahead)
            if check_date.weekday() < 5:  # Monday to Friday
                available_slots.append({
                    'date': check_date.strftime('%Y-%m-%d'),
                    'formatted_date': check_date.strftime('%d de %B').lower()
                })
            days_ahead += 1
        return available_slots

    # Get available times for specific date
    date_obj = datetime.strptime(date, '%Y-%m-%d')
    if date_obj.date() < now.date():
        return []

    # Business hours: 9:00 to 17:00
    times = []
    start_time = time(9, 0)
    end_time = time(17, 0)
    interval = timedelta(minutes=30)

    current_time = datetime.combine(date_obj.date(), start_time)
    while current_time.time() <= end_time:
        # Check if slot is already booked
        existing_appointment = Appointment.query.filter_by(
            date=date_obj.date(),
            time=current_time.strftime('%H:%M')
        ).first()

        if not existing_appointment:
            times.append(current_time.strftime('%H:%M'))
        
        current_time += interval

    return times

def format_message(text, session=None):
    """Format message with progress bar if session provided"""
    if not session:
        return text
    return f"{text}{session.get_progress()}"

def handle_booking_flow(user_input, current_state, booking_data):
    """Handle the step-by-step booking flow"""
    session = BookingSession()
    session.state = current_state
    session.data = booking_data or {}

    if current_state == CONVERSATION_STATES['INITIAL']:
        session.update_state(CONVERSATION_STATES['COLLECTING_NAME'])
        return format_message(
            "👋 ¡Hola! Me alegro de poder ayudarte a agendar una cita. "
            "Para empezar, ¿podrías decirme tu nombre completo?",
            session
        )

    elif current_state == CONVERSATION_STATES['COLLECTING_NAME']:
        if not validate_name(user_input):
            return format_message(
                "❌ Por favor, ingresa un nombre válido usando solo letras y espacios. "
                "Por ejemplo: Juan Pérez",
                session
            )

        session.data['name'] = user_input
        session.update_state(CONVERSATION_STATES['COLLECTING_EMAIL'])
        return format_message(
            f"✅ Gracias {user_input}. Ahora necesito tu correo electrónico para enviarte "
            "la confirmación de la cita.",
            session
        )

    elif current_state == CONVERSATION_STATES['COLLECTING_EMAIL']:
        if not validate_email(user_input):
            return format_message(
                "❌ Por favor, ingresa una dirección de correo electrónico válida. "
                "Por ejemplo: nombre@empresa.com",
                session
            )

        session.data['email'] = user_input
        session.update_state(CONVERSATION_STATES['SELECTING_SERVICE'])
        
        services_text = "\n".join(
            f"{i+1}. {service}" 
            for i, service in enumerate(SERVICES)
        )
        return format_message(
            "✅ Perfecto. ¿Qué tipo de servicio te interesa?\n\n"
            f"{services_text}\n\n"
            "Por favor, selecciona el número del servicio deseado.",
            session
        )

    elif current_state == CONVERSATION_STATES['SELECTING_SERVICE']:
        try:
            service_index = int(user_input) - 1
            if not (0 <= service_index < len(SERVICES)):
                raise ValueError()
        except (ValueError, TypeError):
            services_text = "\n".join(
                f"{i+1}. {service}"
                for i, service in enumerate(SERVICES)
            )
            return format_message(
                "❌ Por favor, selecciona un número válido de la lista:\n\n"
                f"{services_text}",
                session
            )

        session.data['service'] = SERVICES[service_index]
        session.update_state(CONVERSATION_STATES['SELECTING_DATE'])
        
        available_slots = get_available_slots()
        dates_text = "\n".join(
            f"{i+1}. {slot['formatted_date']}"
            for i, slot in enumerate(available_slots)
        )
        
        return format_message(
            "✅ Excelente elección. Estas son las fechas disponibles:\n\n"
            f"{dates_text}\n\n"
            "Por favor, selecciona el número de la fecha que prefieres.",
            session
        )

    elif current_state == CONVERSATION_STATES['SELECTING_DATE']:
        available_slots = get_available_slots()
        try:
            date_index = int(user_input) - 1
            if not (0 <= date_index < len(available_slots)):
                raise ValueError()
        except (ValueError, TypeError):
            dates_text = "\n".join(
                f"{i+1}. {slot['formatted_date']}"
                for i, slot in enumerate(available_slots)
            )
            return format_message(
                "❌ Por favor, selecciona un número válido de la lista:\n\n"
                f"{dates_text}",
                session
            )

        selected_date = available_slots[date_index]
        session.data['date'] = selected_date['date']
        session.data['formatted_date'] = selected_date['formatted_date']
        session.update_state(CONVERSATION_STATES['SELECTING_TIME'])

        available_times = get_available_slots(selected_date['date'])
        times_text = "\n".join(
            f"{i+1}. {time}"
            for i, time in enumerate(available_times)
        )

        return format_message(
            f"✅ Has seleccionado el {selected_date['formatted_date']}. "
            "Estos son los horarios disponibles:\n\n"
            f"{times_text}\n\n"
            "Por favor, selecciona el número del horario que prefieres.",
            session
        )

    elif current_state == CONVERSATION_STATES['SELECTING_TIME']:
        available_times = get_available_slots(session.data['date'])
        try:
            time_index = int(user_input) - 1
            if not (0 <= time_index < len(available_times)):
                raise ValueError()
        except (ValueError, TypeError):
            times_text = "\n".join(
                f"{i+1}. {time}"
                for i, time in enumerate(available_times)
            )
            return format_message(
                "❌ Por favor, selecciona un número válido de la lista:\n\n"
                f"{times_text}",
                session
            )

        session.data['time'] = available_times[time_index]
        session.update_state(CONVERSATION_STATES['CONFIRMATION'])

        return format_message(
            "🎉 ¡Perfecto! Por favor, revisa los detalles de tu cita:\n\n"
            f"👤 Nombre: {session.data['name']}\n"
            f"📧 Email: {session.data['email']}\n"
            f"🔧 Servicio: {session.data['service']}\n"
            f"📅 Fecha: {session.data['formatted_date']}\n"
            f"🕒 Hora: {session.data['time']}\n\n"
            "¿Confirmas esta cita? (Responde 'sí' para confirmar o 'no' para cancelar)",
            session
        )

    elif current_state == CONVERSATION_STATES['CONFIRMATION']:
        if user_input.lower() not in ['si', 'sí', 'yes', 's']:
            return "❌ Cita cancelada. ¿Deseas comenzar de nuevo?"

        try:
            # Create appointment
            appointment = Appointment(
                name=session.data['name'],
                email=session.data['email'],
                date=datetime.strptime(session.data['date'], '%Y-%m-%d').date(),
                time=session.data['time'],
                service=session.data['service']
            )

            # Save to database
            db.session.add(appointment)
            db.session.commit()

            # Send confirmation email
            send_appointment_confirmation(appointment)
            schedule_reminder_email(appointment)

            return (
                "✅ ¡Tu cita ha sido confirmada! Te hemos enviado un correo electrónico "
                "con los detalles de la cita. ¿Hay algo más en lo que pueda ayudarte?\n\n"
                "BOOKING_COMPLETE"
            )
        except Exception as e:
            logger.error(f"Error creating appointment: {str(e)}")
            return (
                "❌ Lo siento, ha ocurrido un error al agendar la cita. "
                "Por favor, intenta nuevamente."
            )

    return "❌ Lo siento, ha ocurrido un error. ¿Podrías intentarlo de nuevo?"

def generate_response(message, conversation_history=[]):
    """Generate chatbot response"""
    if not message:
        return "Por favor, ingresa un mensaje."

    # Extract state and data from conversation history
    current_state = CONVERSATION_STATES['INITIAL']
    booking_data = {}

    if conversation_history:
        last_bot_message = next(
            (msg['text'] for msg in reversed(conversation_history) if not msg['is_user']),
            None
        )
        if last_bot_message:
            state_match = re.search(r'__STATE__(\w+)__', last_bot_message)
            data_match = re.search(r'__DATA__({.*?})__', last_bot_message)
            
            if state_match:
                current_state = state_match.group(1)
            if data_match:
                try:
                    booking_data = json.loads(data_match.group(1))
                except json.JSONDecodeError:
                    pass

    # Handle booking flow
    return handle_booking_flow(message, current_state, booking_data)
