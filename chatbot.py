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

# Booking states and services remain the same
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
    and negative pattern matching
    """
    message_lower = message.lower()
    
    # Negative patterns - exclude general inquiries
    negative_patterns = [
        r'(?:cuanto|cuánto)\s+(?:cuesta|vale|es)',
        r'(?:que|qué)\s+(?:es|son|incluye)',
        r'(?:como|cómo)\s+(?:funciona|aplica)',
        r'requisitos',
        r'empleados?\s+(?:necesito|requiere|pide)',
        r'información',
        r'duda'
    ]
    
    # If message matches any negative pattern, it's likely a general question
    if any(re.search(pattern, message_lower) for pattern in negative_patterns):
        return False
        
    # Strong booking intent patterns
    booking_patterns = [
        r'(?:quiero|necesito|deseo)\s+(?:reservar|agendar|programar)',
        r'(?:hacer|solicitar)\s+(?:una|la)\s+(?:cita|consulta|reunión)',
        r'(?:me\s+gustaría|quisiera)\s+(?:tener|agendar)\s+(?:una|la)\s+(?:cita|consulta)',
        r'(?:puedo|podría|podrías)\s+(?:reservar|agendar)\s+(?:ahora|ya)',
    ]
    
    # Direct booking keywords with context
    booking_keywords = [
        'reservar cita',
        'agendar cita',
        'programar reunión',
        'solicitar consulta',
        'hacer una cita'
    ]
    
    # Check for strong booking intent
    if any(keyword in message_lower for keyword in booking_keywords):
        return True
        
    if any(re.search(pattern, message_lower) for pattern in booking_patterns):
        return True
    
    return False

# BookingSession class and other utility functions remain the same...

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

        # Check for booking completion or cancellation
        if current_state != 'INITIAL':
            last_bot_message = next((msg['text'] for msg in reversed(conversation_history) 
                                   if not msg.get('is_user', True)), '')
            if 'BOOKING_COMPLETE' in last_bot_message or 'BOOKING_CANCELLED' in last_bot_message:
                current_state = 'INITIAL'
                booking_data = {}

        # Handle booking flow
        if current_state != 'INITIAL' or detect_appointment_intent(user_message):
            session = BookingSession()
            session.state = current_state
            session.data = booking_data
            return handle_booking_step(user_message, session)

        # Enhanced system prompt for better context awareness and eligibility handling
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres el asistente virtual de KIT CONSULTING, especializado en ayudas "
                    "gubernamentales para la transformación digital de empresas. "
                    "\n\nREQUISITOS DE ELEGIBILIDAD:\n"
                    "- Empleados: Mínimo 10 empleados, máximo 249\n"
                    "- Domicilio fiscal en territorio español\n"
                    "- Estar inscrito en el censo de empresarios\n"
                    "- No tener consideración de empresa en crisis\n"
                    "\n\nSEGMENTOS DE AYUDA:\n"
                    "- Segmento A (10-49 empleados): hasta 12.000€\n"
                    "- Segmento B (50-99 empleados): hasta 18.000€\n"
                    "- Segmento C (100-249 empleados): hasta 24.000€\n"
                    "\n\nCUANDO RESPONDAS SOBRE ELEGIBILIDAD:\n"
                    "1. Si preguntan por menos de 10 empleados:\n"
                    "   - Indica que no son elegibles\n"
                    "   - Sugiere buscar otras ayudas disponibles\n"
                    "2. Si preguntan por servicios específicos:\n"
                    "   - Explica el servicio detalladamente\n"
                    "   - Menciona el importe máximo de ayuda\n"
                    "3. Si cumplen los requisitos:\n"
                    "   - Confirma su elegibilidad\n"
                    "   - Indica el segmento y la ayuda correspondiente\n"
                    "\n\nFormata las respuestas de manera clara y estructurada, usando viñetas o párrafos cortos."
                )
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            role = "user" if msg.get('is_user', True) else "assistant"
            content = msg['text']
            if role == "assistant" and '__STATE__' in content:
                content = content.split('__STATE__')[0].strip()
            messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": user_message})

        # Generate response using OpenAI
        completion = openai.ChatCompletion.create(
            model="gpt-4",
            messages=messages,
            max_tokens=500,
            temperature=0.7
        )

        response = completion.choices[0].message.content.strip()

        # Only suggest booking if it's a positive eligibility case
        if "elegible" in response.lower() and "no" not in response.lower():
            response += "\n\n¿Te gustaría agendar una consultoría personalizada para discutir tu caso específico?"

        return response

    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Lo siento, estoy experimentando dificultades técnicas. Por favor, intenta de nuevo en unos momentos."

# Rest of the code (handle_booking_step, etc.) remains the same...
