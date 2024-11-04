import os
import openai
from datetime import datetime, timedelta
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from dotenv import load_dotenv
import re
import json

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

class ChatSession:
    def __init__(self):
        self.state = 'INITIAL'
        self.data = {}
    
    def update_state(self, new_state, new_data=None):
        self.state = new_state
        if new_data:
            self.data.update(new_data)
    
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

# Available services
SERVICES = [
    "Inteligencia Artificial (hasta 6.000€)",
    "Ventas Digitales (hasta 6.000€)",
    "Estrategia y Rendimiento de Negocio (hasta 6.000€)"
]

# Company information
COMPANY_INFO = """
Somos Navegatel, una empresa especializada en asesoría digital, expertos en el programa KIT CONSULTING...
[rest of the company info remains the same]
"""

def validate_name(name):
    return bool(re.match("^[A-Za-zÀ-ÿ\s]{2,100}$", name))

def validate_email(email):
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))

def validate_phone(phone):
    return bool(re.match(r"^(?:\+34|0034|34)?[6789]\d{8}$", phone))

def get_available_slots():
    slots = []
    current_date = datetime.now()
    days_ahead = 0
    
    while len(slots) < 7:
        check_date = current_date + timedelta(days=days_ahead)
        if check_date.weekday() < 5:  # Monday = 0, Friday = 4
            slots.append({
                'date': check_date.strftime("%Y-%m-%d"),
                'times': ["10:30", "11:00", "11:30", "12:00", "12:30", "13:00", "13:30", "14:00"]
            })
        days_ahead += 1
    
    return slots

def handle_booking_flow(user_input, current_state, booking_data):
    session = ChatSession()
    session.state = current_state
    session.data = booking_data or {}
    
    if current_state == 'INITIAL':
        session.update_state('COLLECTING_NAME')
        return (
            "¡Excelente elección! La Inteligencia Artificial es un servicio muy potente para la transformación digital de tu "
            "empresa. Para agendar una cita, necesito algunos datos. Por favor, proporcióneme tu nombre." + 
            session.get_state_data()
        )
    
    elif current_state == 'COLLECTING_NAME':
        if not validate_name(user_input):
            return (
                "El nombre proporcionado no parece válido. Por favor, ingresa tu nombre completo usando solo letras." +
                session.get_state_data()
            )
        
        session.update_state('COLLECTING_EMAIL', {'name': user_input})
        return (
            "Gracias. Ahora necesito tu correo electrónico para enviarte la confirmación de la cita." +
            session.get_state_data()
        )
    
    # [Rest of the states follow the same pattern]
    # For brevity, I'll show one more example and you can apply the same pattern to others
    
    elif current_state == 'COLLECTING_EMAIL':
        if not validate_email(user_input):
            return (
                "El correo electrónico no parece válido. Por favor, ingresa una dirección de correo válida." +
                session.get_state_data()
            )
        
        session.update_state('COLLECTING_PHONE', {'email': user_input})
        return (
            "Perfecto. Ahora necesito tu número de teléfono para contactarte si es necesario." +
            session.get_state_data()
        )
    
    # [Other states continue with the same pattern]
    # The important change is that we now append the state data at the end of each message
    # and it will be stripped before showing to the user

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

        # Handle appointment booking flow
        if current_state != 'INITIAL' or 'cita' in user_message.lower():
            full_response = handle_booking_flow(user_message, current_state, booking_data)
            # Extract user message and state data
            if '__STATE__' in full_response:
                user_message = full_response.split('__STATE__')[0]
                return full_response
            return full_response

        # Regular chatbot response logic remains the same
        messages = [
            {
                "role": "system",
                "content": f"Eres el asistente virtual de Navegatel... [rest remains the same]"
            }
        ]

        # Add conversation history (excluding state data)
        for msg in conversation_history:
            content = msg['text']
            if not msg.get('is_user', True) and '__STATE__' in content:
                content = content.split('__STATE__')[0]
            messages.append({"role": "user" if msg["is_user"] else "assistant", "content": content})

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
        
        # Update metrics
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
