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

# Metrics tracking
metrics = {
    "total_queries": 0,
    "successful_queries": 0,
    "failed_queries": 0,
    "response_times": [],
    "daily_stats": {},
    "error_types": {}
}

SERVICES = [
    "Inteligencia Artificial (hasta 6.000€)",
    "Ventas Digitales (hasta 6.000€)",
    "Estrategia y Rendimiento de Negocio (hasta 6.000€)"
]

class ChatSession:
    def __init__(self):
        self.state = 'INITIAL'
        self.data = {}
        self.total_steps = 6  # Total number of steps in booking process
        self.current_step = 0
    
    def update_state(self, new_state, new_data=None):
        self.state = new_state
        if new_data:
            self.data.update(new_data)
        # Update progress based on state
        self.current_step = {
            'INITIAL': 0,
            'COLLECTING_NAME': 1,
            'COLLECTING_EMAIL': 2,
            'COLLECTING_PHONE': 3,
            'SELECTING_DATE': 4,
            'SELECTING_TIME': 5,
            'SELECTING_SERVICE': 6,
            'CONFIRMATION': 6
        }.get(new_state, 0)
    
    def get_progress_bar(self):
        if self.state == 'INITIAL':
            return ""
        progress = (self.current_step / self.total_steps) * 100
        return f"\n\nProgreso: {progress:.0f}% completado"
    
    def get_state_data(self):
        return f"__STATE__{self.state}__DATA__{json.dumps(self.data)}__END__"

    @staticmethod
    def extract_state_data(message):
        if '__STATE__' not in message:
            return None, None
        try:
            state = message.split('__STATE__')[1].split('__DATA__')[0]
            data_str = message.split('__DATA__')[1].split('__END__')[0]
            data = json.loads(data_str)
            return state, data
        except:
            return None, None

def validate_name(name):
    return bool(re.match("^[A-Za-zÀ-ÿ\s]{2,100}$", name))

def validate_email(email):
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))

def validate_phone(phone):
    # Optional phone validation - can be empty
    if not phone:
        return True
    return bool(re.match(r"^(?:\+34|0034|34)?[6789]\d{8}$", phone))

def format_date_spanish(date_str):
    try:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%-d de %B, %Y').lower()
    except:
        return date_str

def get_available_slots():
    """Get available time slots checking for conflicts"""
    slots = []
    current_date = datetime.now()
    days_ahead = 0
    
    while len(slots) < 7:
        check_date = current_date + timedelta(days=days_ahead)
        if check_date.weekday() < 5:  # Monday = 0, Friday = 4
            # Get booked appointments for this date
            booked_times = set(
                apt.time for apt in Appointment.query.filter_by(
                    date=check_date.date()
                ).all()
            )
            
            # All possible 30-min slots
            all_times = []
            current_time = datetime.strptime("10:30", "%H:%M")
            end_time = datetime.strptime("14:00", "%H:%M")
            
            while current_time <= end_time:
                time_str = current_time.strftime("%H:%M")
                if time_str not in booked_times:
                    all_times.append(time_str)
                current_time += timedelta(minutes=30)
            
            if all_times:  # Only add dates that have available slots
                slots.append({
                    'date': check_date.strftime("%Y-%m-%d"),
                    'formatted_date': format_date_spanish(check_date.strftime("%Y-%m-%d")),
                    'times': all_times
                })
        days_ahead += 1
    
    return slots

def handle_booking_flow(user_input, current_state, booking_data):
    """Handle the step-by-step booking flow with improved user experience"""
    session = ChatSession()
    session.state = current_state
    session.data = booking_data or {}
    
    if current_state == 'INITIAL':
        session.update_state('COLLECTING_NAME')
        return (
            "¡Excelente elección! Para ayudarte a agendar una cita, necesito algunos datos. "
            "Por favor, introduce tu nombre completo." + 
            session.get_progress_bar() +
            session.get_state_data()
        )
    
    elif current_state == 'COLLECTING_NAME':
        if not validate_name(user_input):
            return (
                "El nombre proporcionado no es válido. Por favor, ingresa tu nombre completo "
                "usando solo letras (por ejemplo: Juan Pérez Martínez)." +
                session.get_progress_bar() +
                session.get_state_data()
            )
        
        session.update_state('COLLECTING_EMAIL', {'name': user_input})
        return (
            f"Gracias {user_input}. Ahora necesito tu correo electrónico para enviarte "
            "la confirmación de la cita." +
            session.get_progress_bar() +
            session.get_state_data()
        )
    
    elif current_state == 'COLLECTING_EMAIL':
        if not validate_email(user_input):
            return (
                "El correo electrónico no es válido. Por favor, ingresa una dirección "
                "de correo válida (por ejemplo: nombre@dominio.com)." +
                session.get_progress_bar() +
                session.get_state_data()
            )
        
        session.update_state('COLLECTING_PHONE', {'email': user_input})
        return (
            "Perfecto. ¿Podrías proporcionarme un número de teléfono para contactarte en caso necesario? "
            "(Este campo es opcional, puedes escribir 'saltar' para continuar)." +
            session.get_progress_bar() +
            session.get_state_data()
        )
    
    elif current_state == 'COLLECTING_PHONE':
        if user_input.lower() == 'saltar':
            user_input = ''
        
        if not validate_phone(user_input):
            return (
                "El número de teléfono no es válido. Por favor, ingresa un número español válido "
                "o escribe 'saltar' para continuar sin teléfono." +
                session.get_progress_bar() +
                session.get_state_data()
            )
        
        session.update_state('SELECTING_DATE', {'phone': user_input})
        slots = get_available_slots()
        
        if not slots:
            return (
                "Lo siento, no hay fechas disponibles en los próximos días. "
                "Por favor, intenta más tarde." +
                session.get_state_data()
            )
        
        dates_text = "\n".join(
            f"{i+1}. {slot['formatted_date']}"
            for i, slot in enumerate(slots)
        )
        
        return (
            f"Gracias. Estas son las fechas disponibles:\n\n{dates_text}\n\n"
            "Por favor, selecciona el número de la fecha que prefieres." +
            session.get_progress_bar() +
            session.get_state_data()
        )
    
    elif current_state == 'SELECTING_DATE':
        try:
            slots = get_available_slots()
            date_index = int(user_input) - 1
            if 0 <= date_index < len(slots):
                selected_date = slots[date_index]
                session.data['date'] = selected_date['date']
                session.data['formatted_date'] = selected_date['formatted_date']
                
                times_text = "\n".join(
                    f"{i+1}. {time}"
                    for i, time in enumerate(selected_date['times'])
                )
                
                session.update_state('SELECTING_TIME')
                return (
                    f"Has seleccionado el {selected_date['formatted_date']}. "
                    f"Estos son los horarios disponibles:\n\n{times_text}\n\n"
                    "Por favor, selecciona el número del horario que prefieres." +
                    session.get_progress_bar() +
                    session.get_state_data()
                )
        except:
            pass
        
        dates_text = "\n".join(
            f"{i+1}. {slot['formatted_date']}"
            for i, slot in enumerate(slots)
        )
        return (
            "Por favor, selecciona un número válido de la lista:\n\n" +
            dates_text +
            session.get_progress_bar() +
            session.get_state_data()
        )
    
    elif current_state == 'SELECTING_TIME':
        try:
            slots = get_available_slots()
            selected_slot = next(
                slot for slot in slots 
                if slot['date'] == session.data['date']
            )
            time_index = int(user_input) - 1
            
            if 0 <= time_index < len(selected_slot['times']):
                session.data['time'] = selected_slot['times'][time_index]
                session.update_state('SELECTING_SERVICE')
                
                services_text = "\n".join(
                    f"{i+1}. {service}"
                    for i, service in enumerate(SERVICES)
                )
                
                return (
                    f"Has seleccionado las {session.data['time']}. "
                    "¿Qué servicio te interesa?\n\n" +
                    services_text + "\n\n"
                    "Por favor, selecciona el número del servicio deseado." +
                    session.get_progress_bar() +
                    session.get_state_data()
                )
        except:
            pass
        
        times_text = "\n".join(
            f"{i+1}. {time}"
            for i, time in enumerate(selected_slot['times'])
        )
        return (
            "Por favor, selecciona un número válido de la lista:\n\n" +
            times_text +
            session.get_progress_bar() +
            session.get_state_data()
        )
    
    elif current_state == 'SELECTING_SERVICE':
        try:
            service_index = int(user_input) - 1
            if 0 <= service_index < len(SERVICES):
                session.data['service'] = SERVICES[service_index]
                session.update_state('CONFIRMATION')
                
                phone_info = (
                    f"Teléfono: {session.data['phone']}\n"
                    if session.data.get('phone')
                    else "Teléfono: No proporcionado\n"
                )
                
                return (
                    "¡Perfecto! Por favor, revisa los detalles de tu cita:\n\n"
                    f"Nombre: {session.data['name']}\n"
                    f"Email: {session.data['email']}\n" +
                    phone_info +
                    f"Fecha: {session.data['formatted_date']}\n"
                    f"Hora: {session.data['time']}\n"
                    f"Servicio: {session.data['service']}\n\n"
                    "¿Confirmas esta cita? (Responde 'sí' para confirmar o 'no' para cancelar)" +
                    session.get_progress_bar() +
                    session.get_state_data()
                )
        except:
            pass
        
        services_text = "\n".join(
            f"{i+1}. {service}"
            for i, service in enumerate(SERVICES)
        )
        return (
            "Por favor, selecciona un número válido de la lista:\n\n" +
            services_text +
            session.get_progress_bar() +
            session.get_state_data()
        )
    
    elif current_state == 'CONFIRMATION':
        if user_input.lower() in ['si', 'sí', 'yes']:
            try:
                # Create appointment in database
                appointment = Appointment(
                    name=session.data['name'],
                    email=session.data['email'],
                    date=datetime.strptime(session.data['date'], '%Y-%m-%d').date(),
                    time=session.data['time'],
                    service=session.data['service']
                )
                db.session.add(appointment)
                db.session.commit()
                
                # Send confirmation email
                send_appointment_confirmation(appointment)
                schedule_reminder_email(appointment)
                
                return (
                    "¡Tu cita ha sido confirmada! Te hemos enviado un correo electrónico "
                    "con los detalles. ¿Hay algo más en lo que pueda ayudarte?" +
                    "\n\nBOOKING_COMPLETE" +
                    session.get_state_data()
                )
            except Exception as e:
                logger.error(f"Error creating appointment: {str(e)}")
                return (
                    "Lo siento, ha ocurrido un error al procesar tu cita. "
                    "Por favor, intenta de nuevo más tarde." +
                    session.get_state_data()
                )
        elif user_input.lower() in ['no', 'cancel', 'cancelar']:
            return (
                "De acuerdo, he cancelado la reserva. "
                "¿Hay algo más en lo que pueda ayudarte?" +
                "\n\nBOOKING_CANCELLED" +
                session.get_state_data()
            )
        else:
            return (
                "Por favor, responde 'sí' para confirmar la cita o 'no' para cancelarla." +
                session.get_progress_bar() +
                session.get_state_data()
            )
    
    return (
        "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo." +
        session.get_state_data()
    )

def get_chat_response(user_message, conversation_history=None):
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
                state, data = ChatSession.extract_state_data(msg['text'])
                if state:
                    current_state = state
                    booking_data = data or {}

        # Check if we need to handle booking flow
        if current_state != 'INITIAL' or 'cita' in user_message.lower():
            full_response = handle_booking_flow(user_message, current_state, booking_data)
            return full_response

        # Regular chatbot response
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres el asistente virtual de Navegatel, especializado en el programa KIT CONSULTING. "
                    "Tu objetivo es ayudar a los usuarios a entender el programa de ayudas y guiarlos "
                    "en el proceso de solicitud. Si el usuario muestra interés, especialmente en IA, "
                    "sugiérele agendar una cita."
                )
            }
        ]

        # Add conversation history (excluding state data)
        for msg in conversation_history:
            content = msg['text']
            if not msg.get('is_user', True) and '__STATE__' in content:
                content = content.split('__STATE__')[0]
            messages.append({
                "role": "user" if msg["is_user"] else "assistant",
                "content": content
            })

        messages.append({"role": "user", "content": user_message})

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
            presence_penalty=0.6
        )

        return response.choices[0].message["content"]

    except Exception as e:
        logger.error(f"Error in get_chat_response: {str(e)}", exc_info=True)
        return "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo."

def generate_response(message, conversation_history=None):
    start_time = datetime.now()
    success = False
    
    try:
        if not message.strip():
            return "Por favor, escribe tu pregunta para poder ayudarte."
            
        response = get_chat_response(message, conversation_history)
        success = True
        
        # Strip state data before returning to user
        if '__STATE__' in response:
            user_response = response.split('__STATE__')[0]
            return user_response
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_response: {str(e)}", exc_info=True)
        metrics["error_types"][type(e).__name__] = metrics["error_types"].get(type(e).__name__, 0) + 1
        return "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo."
    
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
