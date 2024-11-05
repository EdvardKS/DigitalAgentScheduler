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

MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

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

def get_available_slots():
    """Get available appointment slots with improved error handling and connection pooling"""
    slots = []
    current_date = datetime.now()
    retries = 0
    
    while retries < MAX_RETRIES:
        try:
            # Get next 7 available weekdays
            for i in range(14):  # Look ahead 14 days to find 7 available slots
                check_date = current_date + timedelta(days=i)
                if check_date.weekday() < 5:  # Monday = 0, Friday = 4
                    with session_scope() as session:
                        # Query appointments for the date
                        appointments = session.query(Appointment).filter(
                            Appointment.date == check_date.date()
                        ).all()
                        booked_times = {apt.time for apt in appointments}
                        
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
                                return slots
            
            # If we get here without errors, break the retry loop
            break
            
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
    
    return slots

def generate_response(user_message, conversation_history=None):
    """Generate chatbot response with improved intent detection and handling"""
    try:
        if not user_message.strip():
            return "Por favor, escribe tu pregunta para poder ayudarte."

        if conversation_history is None:
            conversation_history = []

        # Enhanced system prompt for response generation
        messages = [
            {
                "role": "system",
                "content": (
                    "Eres el asistente virtual de KIT CONSULTING, especializado en ayudas "
                    "gubernamentales para la transformación digital de empresas.\n\n"
                    "REQUISITOS DE ELEGIBILIDAD ESENCIALES:\n"
                    "1. Número de empleados:\n"
                    "   - Mínimo: 10 empleados\n"
                    "   - Máximo: 249 empleados\n"
                    "   - Si preguntan por menos de 10 empleados: Explicar que no son elegibles\n"
                    "\n2. Segmentos de ayuda:\n"
                    "   - Segmento A (10-49 empleados): hasta 12.000€\n"
                    "   - Segmento B (50-99 empleados): hasta 18.000€\n"
                    "   - Segmento C (100-249 empleados): hasta 24.000€\n"
                    "\n3. Otros requisitos:\n"
                    "   - Domicilio fiscal en España\n"
                    "   - Estar inscrito en el censo de empresarios\n"
                    "   - No tener consideración de empresa en crisis\n"
                    "   - Estar al corriente con obligaciones tributarias"
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
            model="gpt-4",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        response = completion.choices[0].message.content.strip()
        return response

    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Lo siento, estoy experimentando dificultades técnicas. Por favor, intenta de nuevo en unos momentos."
