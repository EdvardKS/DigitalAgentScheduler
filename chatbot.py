# Existing imports remain the same
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

# Load environment variables and configure logging
load_dotenv()
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
    'REVIEWING_JSON': 7,
    'CONFIRMATION': 8
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
    
    def format_state_data(self):
        """Format state data for internal use"""
        return f"__STATE__{self.state}__DATA__{json.dumps(self.data)}__END__"
    
    def get_json_summary(self):
        """Generate a formatted JSON summary of the booking"""
        summary = {
            "appointment": {
                "personal_info": {
                    "name": self.data.get('name', ''),
                    "email": self.data.get('email', ''),
                    "phone": self.data.get('phone', 'No proporcionado')
                },
                "service": self.data.get('service', ''),
                "schedule": {
                    "date": self.data.get('formatted_date', ''),
                    "time": self.data.get('time', '')
                }
            }
        }
        return json.dumps(summary, indent=2, ensure_ascii=False)
    
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

def format_list_html(items, prefix=""):
    """Helper function to format lists as HTML"""
    if not items:
        return ""
    list_items = "\n".join([f"<li>{prefix}{i+1}. {item}</li>" for i, item in enumerate(items)])
    return f"<ul>\n{list_items}\n</ul>"

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
    """Handle each step of the booking process with improved formatting"""
    
    error_messages = {
        'name': "<strong>Por favor, ingresa un nombre válido usando solo letras</strong> (ejemplo: Juan Pérez).",
        'email': "<strong>Por favor, ingresa un correo electrónico válido</strong> (ejemplo: nombre@dominio.com).",
        'phone': "<strong>Por favor, ingresa un número de teléfono español válido o escribe 'saltar'</strong>.",
        'service_index': "<strong>Por favor, selecciona un número válido de la lista de servicios.</strong>",
        'date_index': "<strong>Por favor, selecciona un número válido de la lista de fechas.</strong>",
        'time_index': "<strong>Por favor, selecciona un número válido de la lista de horarios.</strong>",
        'confirmation': "<strong>Por favor, responde 'sí' para confirmar o 'no' para cancelar.</strong>"
    }

    def create_response(message):
        """Helper to create response with hidden state data"""
        return message + session.format_state_data()
    
    if session.state == 'INITIAL':
        session.state = 'COLLECTING_NAME'
        return create_response(
            "<strong>¡Bienvenido al sistema de reservas!</strong>\n\n"
            "Para ayudarte a agendar una cita, necesito algunos datos.\n\n"
            "<strong>Por favor, introduce tu nombre completo:</strong>"
        )
    
    elif session.state == 'COLLECTING_NAME':
        if not validate_input('name', user_input):
            return create_response(error_messages['name'])
        
        session.data['name'] = user_input
        session.state = 'COLLECTING_EMAIL'
        return create_response(
            f"Gracias <strong>{user_input}</strong>.\n\n"
            "<strong>Por favor, introduce tu correo electrónico para enviarte "
            "la confirmación de la cita:</strong>"
        )
    
    elif session.state == 'COLLECTING_EMAIL':
        if not validate_input('email', user_input):
            return create_response(error_messages['email'])
        
        session.data['email'] = user_input
        session.state = 'COLLECTING_PHONE'
        return create_response(
            "<strong>¿Podrías proporcionarme un número de teléfono para contactarte en caso necesario?</strong>\n"
            "(Este campo es opcional, puedes escribir 'saltar' para continuar)"
        )
    
    elif session.state == 'COLLECTING_PHONE':
        if user_input.lower() == 'saltar':
            user_input = ''
            
        if not validate_input('phone', user_input):
            return create_response(error_messages['phone'])
        
        session.data['phone'] = user_input
        session.state = 'SELECTING_SERVICE'
        
        services_html = format_list_html(SERVICES)
        
        return create_response(
            "<strong>¿Qué servicio te interesa?</strong>\n\n" +
            services_html + "\n\n"
            "<strong>Por favor, selecciona el número del servicio deseado:</strong>"
        )
    
    elif session.state == 'SELECTING_SERVICE':
        if not validate_input('service_index', user_input):
            return create_response(error_messages['service_index'])
        
        service_index = int(user_input) - 1
        session.data['service'] = SERVICES[service_index]
        session.state = 'SELECTING_DATE'
        
        slots = get_available_slots()
        if not slots:
            return create_response(
                "<strong>Lo siento, no hay fechas disponibles en los próximos días.</strong>\n"
                "Por favor, intenta más tarde."
            )
        
        dates_html = format_list_html([slot['formatted_date'] for slot in slots])
        
        return create_response(
            f"Has seleccionado: <strong>{session.data['service']}</strong>\n\n"
            "<strong>Estas son las fechas disponibles:</strong>\n" +
            dates_html + "\n"
            "<strong>Por favor, selecciona el número de la fecha que prefieres:</strong>"
        )
    
    elif session.state == 'SELECTING_DATE':
        if not validate_input('date_index', user_input):
            return create_response(error_messages['date_index'])
        
        slots = get_available_slots()
        date_index = int(user_input) - 1
        
        if date_index < 0 or date_index >= len(slots):
            return create_response(error_messages['date_index'])
        
        selected_date = slots[date_index]
        session.data['date'] = selected_date['date']
        session.data['formatted_date'] = selected_date['formatted_date']
        session.state = 'SELECTING_TIME'
        
        times_html = format_list_html(selected_date['times'])
        
        return create_response(
            f"Has seleccionado el <strong>{selected_date['formatted_date']}</strong>.\n\n"
            "<strong>Estos son los horarios disponibles:</strong>\n" +
            times_html + "\n"
            "<strong>Por favor, selecciona el número del horario que prefieres:</strong>"
        )
    
    elif session.state == 'SELECTING_TIME':
        if not validate_input('time_index', user_input):
            return create_response(error_messages['time_index'])
        
        slots = get_available_slots()
        selected_slot = next(
            slot for slot in slots 
            if slot['date'] == session.data['date']
        )
        
        time_index = int(user_input) - 1
        if time_index < 0 or time_index >= len(selected_slot['times']):
            return create_response(error_messages['time_index'])
        
        session.data['time'] = selected_slot['times'][time_index]
        session.state = 'REVIEWING_JSON'
        
        # Generate JSON summary
        json_summary = session.get_json_summary()
        
        return create_response(
            "<strong>Resumen de tu cita:</strong>\n\n"
            "<pre><code>" + json_summary + "</code></pre>\n\n"
            "<strong>¿Los datos son correctos?</strong> (Responde 'sí' para confirmar o 'no' para cancelar)"
        )
    
    elif session.state == 'REVIEWING_JSON':
        if not validate_input('confirmation', user_input):
            return create_response(error_messages['confirmation'])
        
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
                
                return create_response(
                    "<strong>¡Tu cita ha sido confirmada!</strong>\n\n"
                    "Te hemos enviado un correo electrónico con los detalles.\n"
                    "También recibirás un recordatorio 24 horas antes de la cita.\n\n"
                    "¿Hay algo más en lo que pueda ayudarte?" +
                    "\n\nBOOKING_COMPLETE"
                )
            except Exception as e:
                logger.error(f"Error creating appointment: {str(e)}")
                return create_response(
                    "<strong>Lo siento, ha ocurrido un error al procesar tu cita.</strong>\n"
                    "Por favor, intenta de nuevo más tarde."
                )
        else:
            return create_response(
                "<strong>De acuerdo, he cancelado la reserva.</strong>\n\n"
                "¿Hay algo más en lo que pueda ayudarte?" +
                "\n\nBOOKING_CANCELLED"
            )
    
    return create_response(
        "<strong>Lo siento, ha ocurrido un error. Por favor, intenta de nuevo.</strong>"
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
            model=os.getenv("MODELO_FINETUNED"),
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        return completion.choices[0].message.content

    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo más tarde."
