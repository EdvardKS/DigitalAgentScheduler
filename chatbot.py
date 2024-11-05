import os
import openai
from datetime import datetime
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from dotenv import load_dotenv
import re
import json
import locale
from sqlalchemy.exc import SQLAlchemyError

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

SERVICES = [
    "Inteligencia Artificial",
    "Ventas Digitales",
    "Estrategia y Rendimiento de Negocio"
]

def detect_appointment_intent(conversation_history):
    """Use OpenAI to analyze conversation and detect booking intent"""
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a booking intent analyzer. Analyze the conversation "
                    "and determine if the user is trying to schedule an appointment. "
                    "Consider both explicit and implicit booking requests. "
                    "Respond with either 'true' or 'false'."
                )
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            role = "user" if msg.get('is_user', True) else "assistant"
            messages.append({"role": role, "content": msg['text']})

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.1,
            max_tokens=5
        )

        return response.choices[0].message.content.strip().lower() == 'true'

    except Exception as e:
        logger.error(f"Error detecting appointment intent: {str(e)}")
        return False

def validate_appointment_data(data):
    """Validate extracted appointment data"""
    required_fields = {
        'name': r'^[A-Za-zÀ-ÿ\s]{2,100}$',
        'email': r'[^@]+@[^@]+\.[^@]+',
        'service': lambda x: any(s in x for s in SERVICES),
        'date': lambda x: isinstance(x, str) and bool(re.match(r'^\d{4}-\d{2}-\d{2}$', x)),
        'time': lambda x: isinstance(x, str) and bool(re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', x))
    }

    for field, validator in required_fields.items():
        if field not in data or not data[field]:
            return False, f"Missing required field: {field}"
        
        if isinstance(validator, str):
            if not re.match(validator, str(data[field])):
                return False, f"Invalid {field} format"
        elif callable(validator):
            if not validator(data[field]):
                return False, f"Invalid {field} value"

    # Phone is optional but must be valid if provided
    if data.get('phone'):
        if not re.match(r'^(?:\+34)?[6789]\d{8}$', data['phone']):
            return False, "Invalid phone number format"

    return True, None

def process_appointment_data(conversation_history):
    """Extract and process appointment data from conversation"""
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract appointment booking information from the conversation. "
                    "Required fields: name, email, service preference. "
                    "Optional: phone number. "
                    f"Available services: {', '.join(SERVICES)}. "
                    "Format the output as a JSON object with the following structure: "
                    "{'name': str, 'email': str, 'phone': str or null, 'service': str, "
                    "'date': 'YYYY-MM-DD', 'time': 'HH:MM'}. "
                    "If any required field is missing, include a 'missing_fields' array "
                    "in the response."
                )
            }
        ]

        for msg in conversation_history:
            role = "user" if msg.get('is_user', True) else "assistant"
            messages.append({"role": role, "content": msg['text']})

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.1,
            max_tokens=500
        )

        extracted_data = json.loads(response.choices[0].message.content)
        
        # Validate extracted data
        is_valid, error_message = validate_appointment_data(extracted_data)
        if not is_valid:
            return {
                "success": False,
                "error": error_message,
                "data": extracted_data
            }

        return {
            "success": True,
            "data": extracted_data
        }

    except json.JSONDecodeError:
        logger.error("Error parsing OpenAI response as JSON")
        return {"success": False, "error": "Error processing appointment data"}
    except Exception as e:
        logger.error(f"Error processing appointment data: {str(e)}")
        return {"success": False, "error": "Unexpected error processing appointment"}

def create_appointment(appointment_data):
    """Create appointment in database and send confirmations"""
    try:
        appointment = Appointment(
            name=appointment_data['name'],
            email=appointment_data['email'],
            phone=appointment_data.get('phone'),
            date=datetime.strptime(appointment_data['date'], '%Y-%m-%d').date(),
            time=appointment_data['time'],
            service=appointment_data['service'],
            status='Pendiente'
        )

        db.session.add(appointment)
        db.session.commit()

        send_appointment_confirmation(appointment)
        schedule_reminder_email(appointment)

        return True, appointment
    except Exception as e:
        logger.error(f"Error creating appointment: {str(e)}")
        return False, None

def generate_response(message, conversation_history=None):
    """Generate chatbot response with AI-powered appointment booking"""
    try:
        if not message.strip():
            return "Por favor, escribe tu pregunta para poder ayudarte."

        if conversation_history is None:
            conversation_history = []

        # Check for booking intent
        if detect_appointment_intent(conversation_history):
            # Process appointment data
            result = process_appointment_data(conversation_history)
            
            if result['success']:
                # Format confirmation message
                appointment_details = (
                    "<strong>He detectado los siguientes detalles para tu cita:</strong>\n\n"
                    f"Nombre: {result['data']['name']}\n"
                    f"Email: {result['data']['email']}\n"
                    f"Teléfono: {result['data'].get('phone', 'No proporcionado')}\n"
                    f"Servicio: {result['data']['service']}\n"
                    f"Fecha: {result['data']['date']}\n"
                    f"Hora: {result['data']['time']}\n\n"
                    "¿Los datos son correctos? (Responde 'sí' para confirmar o 'no' para corregir)"
                )
                
                success, appointment = create_appointment(result['data'])
                if success:
                    return (
                        "<strong>¡Tu cita ha sido confirmada!</strong>\n\n"
                        "Te hemos enviado un correo electrónico con los detalles.\n"
                        "También recibirás un recordatorio 24 horas antes de la cita.\n\n"
                        "¿Hay algo más en lo que pueda ayudarte?"
                    )
                else:
                    return (
                        "<strong>Lo siento, ha ocurrido un error al procesar tu cita.</strong>\n"
                        "Por favor, inténtalo de nuevo más tarde."
                    )
            else:
                return (
                    "<strong>Necesito algunos detalles adicionales para tu cita:</strong>\n\n"
                    f"{result['error']}\n\n"
                    "¿Podrías proporcionarme esta información?"
                )

        # Handle general inquiries with OpenAI
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
                    "   - Estar al corriente con obligaciones tributarias"
                )
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            role = "user" if msg.get('is_user', True) else "assistant"
            messages.append({"role": role, "content": msg['text']})

        messages.append({"role": "user", "content": message})

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Lo siento, ha ocurrido un error al procesar tu mensaje. Por favor, inténtalo de nuevo."
