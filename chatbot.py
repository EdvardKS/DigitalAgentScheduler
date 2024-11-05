import os
import openai
from datetime import datetime
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from dotenv import load_dotenv
import re
import locale
from booking import BookingSession, handle_booking_step

# Load environment variables and configure logging
load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Set locale for Spanish date formatting
try:
    locale.setlocale(locale.LC_TIME, 'es_ES.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_TIME, 'es_ES')
    except:
        logging.warning("Spanish locale not available, falling back to default")

# Initialize OpenAI
openai.api_key = os.getenv('OPENAI_API_KEY')
if not openai.api_key:
    logger.error("OpenAI API key not found in environment variables")
    raise ValueError("OpenAI API key is required")

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

def generate_response(message, conversation_history):
    """Generate a response to the user's message"""
    try:
        # Check if this is part of an ongoing booking
        if conversation_history:
            last_message = conversation_history[-1]['text']
            state, data = BookingSession.extract_state_data(last_message)
            if state:
                session = BookingSession()
                session.state = state
                session.data = data
                return handle_booking_step(message, session)
        
        # Check for booking intent
        if detect_appointment_intent(message):
            session = BookingSession()
            return handle_booking_step(None, session)
        
        # Otherwise, handle as a general inquiry with OpenAI
        messages = []
        
        # Add conversation history
        for msg in conversation_history:
            role = "assistant" if not msg['is_user'] else "user"
            messages.append({"role": role, "content": msg['text']})
        
        # Add the current message
        messages.append({"role": "user", "content": message})
        
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )
        
        return response.choices[0].message.content
        
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Lo siento, ha ocurrido un error al procesar tu mensaje. Por favor, inténtalo de nuevo."
