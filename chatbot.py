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
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from contextlib import contextmanager
import time

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

# Booking states and services
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

SERVICES = [
    "Inteligencia Artificial",
    "Ventas Digitales",
    "Estrategia y Rendimiento de Negocio"
]

# Maximum retries for database operations
MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

def validate_input(field_type, value):
    """Validate user input based on field type"""
    if not value:
        return False

    if field_type == 'name':
        return bool(re.match("^[A-Za-zÀ-ÿ\s]{2,100}$", value))
    elif field_type == 'email':
        return bool(re.match(r"[^@]+@[^@]+\.[^@]+", value))
    elif field_type == 'phone':
        # Spanish phone number format (optional +34 prefix)
        return bool(re.match(r"^(?:\+34)?[6789]\d{8}$", value))
    elif field_type == 'service':
        return value.isdigit() and 1 <= int(value) <= 3
    elif field_type == 'date':
        try:
            selected_date = int(value)
            return 1 <= selected_date <= 7
        except ValueError:
            return False
    elif field_type == 'time':
        try:
            slots = get_available_slots()
            if slots and slots[0]['times']:
                return value in slots[0]['times']
        except Exception as e:
            logger.error(f"Error validating time: {str(e)}")
        return False
    return False

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = db.session
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()

class BookingSession:
    def __init__(self):
        self.state = 'INITIAL'
        self.data = {}

    def format_state_data(self):
        """Format state data for internal use"""
        return f"__STATE__{self.state}__DATA__{json.dumps(self.data)}__END__"

    @staticmethod
    def extract_state_data(message):
        """Extract state and data from conversation message"""
        if not message or '__STATE__' not in message:
            return None, None
        try:
            state = message.split('__STATE__')[1].split('__DATA__')[0]
            data_str = message.split('__DATA__')[1].split('__END__')[0]
            return state, json.loads(data_str)
        except Exception as e:
            logger.error(f"Error extracting state data: {str(e)}")
            return None, None

def detect_appointment_intent(message):
    """
    Enhanced detection of appointment booking intent with stricter rules
    and improved handling of greetings and general inquiries
    """
    message_lower = message.lower()

    # Negative patterns - exclude greetings, eligibility and general inquiries
    negative_patterns = [
        r'^hola',
        r'^buenos\s+(?:días|tardes|noches)',
        r'^saludos',
        r'^(?:qué\s+tal|que\s+tal)',
        r'^(?:hola\s+)?(?:qué|que)\s+(?:hay|tal)',
        r'tengo\s+\d+\s+empleados',
        r'(?:puedo|podemos|podría)\s+solicitar',
        r'empleados?\s+(?:necesito|requiere|pide)',
        r'(?:soy|somos)\s+elegibles?',
        r'(?:cumplimos?|cumplo)\s+(?:con|los)\s+requisitos',
        r'(?:cuántos|cuantos)\s+empleados',
        r'(?:cuanto|cuánto)\s+(?:cuesta|vale|es)',
        r'(?:que|qué)\s+(?:es|son|incluye)',
        r'(?:como|cómo)\s+(?:funciona|aplica)',
        r'información\s+(?:sobre|del|de)',
        r'requisitos',
        r'dudas?',
        r'consultar?\s+(?:sobre|por)',
        r'(?:me\s+pueden?|pueden?)\s+explicar'
    ]

    if any(re.search(pattern, message_lower) for pattern in negative_patterns):
        return False

    # Strong booking intent patterns - explicit booking requests only
    booking_patterns = [
        r'(?:quiero|necesito|deseo)\s+(?:reservar|agendar|programar)',
        r'(?:hacer|solicitar)\s+(?:una|la)\s+(?:cita|consulta|reunión)',
        r'(?:me\s+gustaría|quisiera)\s+(?:tener|agendar)\s+(?:una|la)\s+(?:cita|consulta)',
        r'(?:puedo|podría|podrías)\s+(?:reservar|agendar)\s+(?:ahora|ya)',
        r'reservar?\s+(?:una|la)\s+(?:cita|consulta)',
        r'agendar?\s+(?:una|la)\s+(?:cita|reunión)',
        r'programar?\s+(?:una|la)\s+(?:cita|consulta)'
    ]

    # Direct booking keywords - explicit intent only
    booking_keywords = [
        'reservar cita',
        'agendar cita',
        'programar reunión',
        'solicitar consulta',
        'hacer una cita'
    ]

    if any(keyword in message_lower for keyword in booking_keywords):
        return True

    if any(re.search(pattern, message_lower) for pattern in booking_patterns):
        return True

    return False

def get_available_slots():
    """Get available appointment slots with improved error handling and session management"""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            slots = []
            current_date = datetime.now()

            with session_scope() as session:
                # Get next 7 available weekdays
                for i in range(14):  # Look ahead 14 days to find 7 available slots
                    check_date = current_date + timedelta(days=i)
                    if check_date.weekday() < 5:  # Monday = 0, Friday = 4
                        # Use the session from context manager
                        booked_times = set(
                            apt.time for apt in session.query(Appointment).filter_by(
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
                                'formatted_date': check_date.strftime('%-d de %B de %Y').lower(),
                                'times': available_times
                            })

                        if len(slots) >= 7:
                            break

            return slots

        except OperationalError as e:
            retries += 1
            logger.error(f"Database connection error (attempt {retries}/{MAX_RETRIES}): {str(e)}")
            if retries < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (2 ** retries))
            else:
                logger.error("Maximum retries reached for database connection")
                raise
        except SQLAlchemyError as e:
            logger.error(f"Database query error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_available_slots: {str(e)}")
            raise

def handle_phone_collection(user_input, session):
    if user_input.lower() == 'saltar':
        user_input = ''
    elif not validate_input('phone', user_input):
        return "Por favor, ingresa un número de teléfono español válido o escribe 'saltar'." + session.format_state_data()

    session.data['phone'] = user_input
    session.state = 'SELECTING_SERVICE'
    return handle_service_selection(None, session)







def handle_service_selection(user_input, session):
    if user_input is not None:
        if not validate_input('service', user_input):
            return "Por favor, selecciona un número válido de la lista." + session.format_state_data()

        service_index = int(user_input) - 1
        session.data['service'] = f"{SERVICES[service_index]} (hasta 6.000€)"
        session.state = 'SELECTING_DATE'

        slots = get_available_slots()
        if not slots:
            return "Lo siento, no hay fechas disponibles en los próximos días." + session.format_state_data()

        dates_list = "\n".join([f"{i+1}. {slot['formatted_date']}" for i, slot in enumerate(slots)])
        return (
            f"Has seleccionado: <strong>{session.data['service']}</strong>\n\n"
            "<strong>Estas son las fechas disponibles:</strong>\n" +
            dates_list + "\n\n"
            "<strong>Por favor, selecciona el número de la fecha que prefieres:</strong>" +
            session.format_state_data()
        )

    return (
        "<strong>¿Qué servicio te interesa?</strong>\n\n"
        "<br>1. Inteligencia Artificial (hasta 6.000€)\n"
        "<br>2. Ventas Digitales (hasta 6.000€)\n"
        "<br>3. Estrategia y Rendimiento de Negocio (hasta 6.000€)\n\n"
        "<strong>Por favor, selecciona el número del servicio deseado:</strong>" +
        session.format_state_data()
    )







def handle_booking_step(user_input, session):
    """Handle each step of the booking process"""
    try:
        if session.state == 'INITIAL':
            session.state = 'COLLECTING_NAME'
            return (
                "<strong>¡Bienvenido al sistema de reservas!</strong>\n\n"
                "Para ayudarte a agendar una cita, necesito algunos datos.\n\n"
                "<strong>Por favor, introduce tu nombre completo:</strong>" +
                session.format_state_data()
            )

        elif session.state == 'COLLECTING_NAME':
            print(session)
            if not validate_input('name', user_input):
                return "Por favor, ingresa un nombre válido usando solo letras." + session.format_state_data()

            session.data['name'] = user_input
            session.state = 'COLLECTING_EMAIL'
            return (
                f"Gracias {user_input}.\n\n"
                "<strong>Por favor, introduce tu correo electrónico para enviarte "
                "la confirmación de la cita:</strong>" +
                session.format_state_data()
            )

        elif session.state == 'COLLECTING_EMAIL':
            print(session)
            if not validate_input('email', user_input):
                return "Por favor, ingresa un correo electrónico válido." + session.format_state_data()

            session.data['email'] = user_input
            session.state = 'COLLECTING_PHONE'
            return (
                "<strong>¿Podrías proporcionarme un número de teléfono para contactarte "
                "en caso necesario?</strong>\n"
                "(Este campo es opcional, puedes escribir 'saltar' para continuar)" +
                session.format_state_data()
            )

        elif session.state == 'COLLECTING_PHONE':
            print(session)
            return handle_phone_collection(user_input, session)

        elif session.state == 'SELECTING_SERVICE':
            print(session)
            return handle_service_selection(user_input, session)

        elif session.state == 'SELECTING_DATE':
            print(session)
            if not validate_input('date', user_input):
                return "Por favor, selecciona un número válido de la lista." + session.format_state_data()

            slots = get_available_slots()
            date_index = int(user_input) - 1

            if date_index < 0 or date_index >= len(slots):
                return "Por favor, selecciona un número válido de la lista." + session.format_state_data()

            selected_date = slots[date_index]
            session.data['date'] = selected_date['date']
            session.data['formatted_date'] = selected_date['formatted_date']
            session.state = 'SELECTING_TIME'

            times_list = "\n".join([f"{i+1}. {time}" for i, time in enumerate(selected_date['times'])])
            return (
                f"Has seleccionado el <strong>{selected_date['formatted_date']}</strong>.\n\n"
                "<strong>Estos son los horarios disponibles:</strong>\n" +
                times_list + "\n\n"
                "<strong>Por favor, selecciona el número del horario que prefieres:</strong>" +
                session.format_state_data()
            )

        elif session.state == 'SELECTING_TIME':
            slots = get_available_slots()
            selected_slot = next(
                slot for slot in slots 
                if slot['date'] == session.data['date']
            )

            time_index = int(user_input) - 1
            if time_index < 0 or time_index >= len(selected_slot['times']):
                return "Por favor, selecciona un número válido de la lista." + session.format_state_data()

            session.data['time'] = selected_slot['times'][time_index]
            session.state = 'CONFIRMATION'

            return (
                "<strong>Resumen de tu cita:</strong>\n\n"
                f"Nombre: {session.data['name']}\n"
                f"Email: {session.data['email']}\n"
                f"Teléfono: {session.data['phone'] or 'No proporcionado'}\n"
                f"Servicio: {session.data['service']}\n"
                f"Fecha: {session.data['formatted_date']}\n"
                f"Hora: {session.data['time']}\n\n"
                "<strong>¿Los datos son correctos?</strong> (Responde 'sí' para confirmar o 'no' para cancelar)" +
                session.format_state_data()
            )

        elif session.state == 'CONFIRMATION':
            if user_input.lower() in ['si', 'sí', 'yes']:
                try:
                    appointment = Appointment(
                        name=session.data['name'],
                        email=session.data['email'],
                        phone=session.data['phone'],
                        date=datetime.strptime(session.data['date'], '%Y-%m-%d').date(),
                        time=session.data['time'],
                        service=session.data['service']
                    )
                    db.session.add(appointment)
                    db.session.commit()

                    send_appointment_confirmation(appointment)
                    schedule_reminder_email(appointment)

                    return (
                        "<strong>¡Tu cita ha sido confirmada!</strong>\n\n"
                        "Te hemos enviado un correo electrónico con los detalles.\n"
                        "También recibirás un recordatorio 24 horas antes de la cita.\n\n"
                        "¿Hay algo más en lo que pueda ayudarte?\n\nBOOKING_COMPLETE"
                    )
                except Exception as e:
                    logger.error(f"Error creating appointment: {str(e)}")
                    return (
                        "<strong>Lo siento, ha ocurrido un error al procesar tu cita.</strong>\n"
                        "Por favor, intenta de nuevo más tarde." +
                        session.format_state_data()
                    )
            else:
                return (
                    "<strong>De acuerdo, he cancelado la reserva.</strong>\n\n"
                    "¿Hay algo más en lo que pueda ayudarte?\n\nBOOKING_CANCELLED"
                )

        return "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo." + session.format_state_data()

    except Exception as e:
        logger.error(f"Error in booking process: {str(e)}")
        return (
            "<strong>Lo siento, ha ocurrido un error inesperado.</strong>\n"
            "Por favor, intenta de nuevo más tarde." +
            session.format_state_data()
        )

def generate_response(user_message, conversation_history=None):
    """Generate chatbot response with improved intent detection and eligibility handling"""
    try:
        if not user_message.strip():
            return "Por favor, escribe tu pregunta para poder ayudarte."

        if conversation_history is None:
            conversation_history = []

        # Extract state data from last bot message
        current_state = 'INITIAL'
        booking_data = {}

        for msg in reversed(conversation_history):
            if not msg.get('is_user', True):
                state, data = BookingSession.extract_state_data(msg['text'])
                if state:
                    current_state = state
                    booking_data = data or {}
                    break

        # Check if we're in a booking flow or if there's a clear booking intent
        if current_state != 'INITIAL' or detect_appointment_intent(user_message):
            session = BookingSession()
            session.state = current_state
            session.data = booking_data
            return handle_booking_step(user_message, session)

        # Enhanced system prompt for eligibility handling
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres el asistente virtual de Navegatel KIT CONSULTING, especializado en ayudas "
                    "gubernamentales para la transformación digital de empresas.\n\n"
                    "REQUISITOS DE ELEGIBILIDAD ESENCIALES:\n"
                    "1. Número de empleados:\n"
                    "   - Mínimo: 10 empleados\n"
                    "   - Máximo: 249 empleados\n"
                    "   - Si preguntan por menos de 10 o más de 250 empleados: Explicar que no son elegibles\n"
                    "\n2. Segmentos de ayuda:\n"
                    "   - Segmento A (10-49 empleados): hasta 12.000€\n"
                    "   - Segmento B (50-99 empleados): hasta 18.000€\n"
                    "   - Segmento C (100-249 empleados): hasta 24.000€\n"
                    "\n3. Otros requisitos:\n"
                    "   - Domicilio fiscal en España\n"
                    "   - Estar inscrito en el censo de empresarios\n"
                    "   - No tener consideración de empresa en crisis\n"
                    "   - Estar al corriente con obligaciones tributarias\n"
                    "\nRESPUESTAS ESPECÍFICAS:\n"
                    "1. Para empresas con menos de 10 empleados:\n"
                    "   'Lo siento, actualmente el programa KIT CONSULTING está diseñado para "
                    "empresas con 10 o más empleados. Para empresas más pequeñas, te recomiendo "
                    "explorar el Kit Digital, que ofrece ayudas específicas para empresas de menor tamaño.'\n"
                    "\n2. Para preguntas sobre empleados:\n"
                    "   - Explicar claramente el requisito mínimo de 10 empleados\n"
                    "   - Detallar el segmento correspondiente y la ayuda disponible\n"
                    "\n3. Para consultas generales:\n"
                    "   - Proporcionar información clara y estructurada\n"
                    "   - Mencionar todos los requisitos relevantes\n"
                    "   - Sugerir agendar una consulta solo si la empresa cumple los requisitos"
                    "IMPORTANTE: Indica que desde el actual chat se puede agendar una cita para un contacto más personal y cercano."
                )
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            role = "user" if msg.get('is_user', True) else "assistant"
            messages.append({"role": role, "content": msg['text']})

        messages.append({"role": "user", "content": user_message})

        # Generate response using OpenAI
        completion = openai.ChatCompletion.create(
            model="ft:gpt-4o-2024-08-06:personal:1-kitconsulting:AOPX7Zzo",
            messages=messages,
            temperature=0.7,
            max_tokens=300
        )

        response = completion.choices[0].message.content.strip()

        # Only suggest booking for eligible companies
        if ("elegible" in response.lower() and 
            "no" not in response.lower() and 
            not any(keyword in user_message.lower() for keyword in ["menos", "9", "8", "7", "6", "5", "4", "3", "2", "1"])):
            response += "\n\n¿Te gustaría agendar una consultoría personalizada para discutir tu caso específico?"

        return response

    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Lo siento, estoy experimentando dificultades técnicas. Por favor, intenta de nuevo en unos momentos."