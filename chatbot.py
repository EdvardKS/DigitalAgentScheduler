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

# Appointment keywords for better detection
APPOINTMENT_KEYWORDS = [
    'cita', 'agendar', 'reservar', 'consulta', 'reunión', 'reunir', 'consultar',
    'disponibilidad', 'horario', 'calendario', 'programar', 'booking', 'fecha'
]

def detect_appointment_intent(message):
    """Detect if the user's message indicates intent to book an appointment"""
    message_lower = message.lower()
    
    # Direct appointment indicators
    for keyword in APPOINTMENT_KEYWORDS:
        if keyword in message_lower:
            return True
            
    # Question patterns that might indicate appointment intent
    appointment_patterns = [
        r'(?:puedo|podría|quisiera|me gustaría|necesito)\s+(?:tener|hacer|agendar|programar)',
        r'(?:cuándo|cuando|que dias|qué horarios|horario)\s+(?:están?|hay|tienen)',
        r'(?:disponible|disponibilidad)',
        r'(?:reunirme|consultarle|hablar)\s+(?:con|al)',
    ]
    
    for pattern in appointment_patterns:
        if re.search(pattern, message_lower):
            return True
            
    return False

def generate_response(user_message, conversation_history=None):
    """Generate chatbot response with improved intent detection"""
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

        # Check if we're in a booking flow or user wants to book
        is_booking_intent = detect_appointment_intent(user_message)
        if current_state != 'INITIAL' or is_booking_intent:
            session = BookingSession()
            session.state = current_state
            session.data = booking_data
            return handle_booking_step(user_message, session)

        # Enhanced system prompt for better context awareness
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres el asistente virtual de KIT CONSULTING, especializado en ayudas "
                    "gubernamentales para la transformación digital de empresas. "
                    "\n\nTu objetivo principal es:\n"
                    "1. Explicar el programa KIT CONSULTING y sus beneficios\n"
                    "2. Guiar sobre los requisitos y proceso de solicitud\n"
                    "3. Informar sobre los servicios disponibles:\n"
                    "   - Inteligencia Artificial (hasta 6.000€)\n"
                    "   - Ventas Digitales (hasta 6.000€)\n"
                    "   - Estrategia y Rendimiento (hasta 6.000€)\n\n"
                    "Si detectas que el usuario:\n"
                    "- Pregunta por servicios específicos → Explica detalladamente\n"
                    "- Muestra interés en costes → Detalla las ayudas por segmento\n"
                    "- Consulta requisitos → Lista los criterios de elegibilidad\n"
                    "- Quiere más información → Sugiere agendar una cita de consultoría\n\n"
                    "Para agendar citas, sugiere: 'Si deseas programar una consultoría "
                    "personalizada, puedo ayudarte a agendar una cita ahora mismo.'"
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

        response = completion.choices[0].message.content

        # If the response mentions booking but we're not in booking flow, suggest it explicitly
        if not current_state == 'INITIAL' and detect_appointment_intent(response):
            response += "\n\n¿Te gustaría agendar una cita ahora? Solo dime 'sí' y te ayudo con el proceso."

        return response

    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo más tarde."
