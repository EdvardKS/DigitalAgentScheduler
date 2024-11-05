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

def get_missing_fields_prompt(missing_fields):
    """Generate natural conversation prompts for missing fields"""
    prompts = {
        'name': "¿Me podrías decir tu nombre completo?",
        'email': "¿Cuál es tu correo electrónico para enviarte la confirmación?",
        'phone': "¿Me proporcionas un número de teléfono de contacto? (opcional)",
        'service': "¿Qué servicio te interesa?\n1. Inteligencia Artificial\n2. Ventas Digitales\n3. Estrategia y Rendimiento",
        'date': "¿Para qué fecha te gustaría programar la cita?",
        'time': "¿En qué horario prefieres la cita?"
    }
    return "\n".join(prompts[field] for field in missing_fields)

def detect_appointment_intent(conversation_history):
    """Use OpenAI to analyze conversation and detect booking intent"""
    try:
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a booking intent analyzer for KIT CONSULTING. "
                    "Analyze the conversation and determine if the user is trying "
                    "to schedule an appointment. Consider both explicit and implicit "
                    "booking requests. Respond with either 'true' or 'false'."
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
                    "You are a booking assistant for KIT CONSULTING. Your task is to extract booking "
                    "information from conversations.\n\n"
                    "IMPORTANT INSTRUCTIONS:\n"
                    "1. Actively look for and extract the following information:\n"
                    "   - Name: Extract full name\n"
                    "   - Email: Look for email address\n"
                    "   - Phone: Extract Spanish format phone number\n"
                    "   - Service preference: Match against available services\n"
                    "   - Date: Extract appointment date\n"
                    "   - Time: Extract appointment time\n\n"
                    "2. If some information is missing, continue conversation to collect it naturally.\n\n"
                    "3. Format response as valid JSON with fields:\n"
                    "   - name\n"
                    "   - email\n"
                    "   - phone (optional)\n"
                    "   - service\n"
                    "   - date\n"
                    "   - time\n\n"
                    "4. Only extract information that's explicitly provided\n\n"
                    "5. Include 'missing_fields' array for any required data not found\n\n"
                    "Example response:\n"
                    "{\n"
                    '  "name": "Juan García",\n'
                    '  "email": "juan@email.com",\n'
                    '  "phone": "+34666777888",\n'
                    '  "service": "Inteligencia Artificial",\n'
                    '  "date": "2024-11-06",\n'
                    '  "time": "10:30",\n'
                    '  "missing_fields": []\n'
                    "}\n\n"
                    f"Available services: {', '.join(SERVICES)}"
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

        # Add response content validation
        content = response.choices[0].message.content.strip()
        if not content:
            logger.error("Empty response from OpenAI")
            return {"success": False, "error": "Empty response from AI model"}

        # Validate response format
        if not (content.startswith('{') and content.endswith('}')):
            logger.error(f"Invalid JSON format in response: {content}")
            return {"success": False, "error": "Invalid response format"}

        try:
            extracted_data = json.loads(content)
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing OpenAI response as JSON: {content}")
            return {"success": False, "error": "Invalid response format"}

        # Check for missing fields
        if 'missing_fields' in extracted_data and extracted_data['missing_fields']:
            return {
                "success": False,
                "error": get_missing_fields_prompt(extracted_data['missing_fields']),
                "missing_fields": extracted_data['missing_fields']
            }

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

    except Exception as e:
        logger.error(f"Error processing appointment data: {str(e)}")
        return {"success": False, "error": "Error inesperado al procesar la cita"}

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
                data = result['data']
                # Format confirmation message
                appointment_details = (
                    "<strong>He detectado los siguientes detalles para tu cita:</strong>\n\n"
                    f"Nombre: {data['name']}\n"
                    f"Email: {data['email']}\n"
                    f"Teléfono: {data.get('phone', 'No proporcionado')}\n"
                    f"Servicio: {data['service']}\n"
                    f"Fecha: {data['date']}\n"
                    f"Hora: {data['time']}\n\n"
                    "¿Los datos son correctos? (Responde 'sí' para confirmar o 'no' para corregir)"
                )
                
                success, appointment = create_appointment(data)
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
                if 'missing_fields' in result:
                    return result['error']
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
                    "Eres el asistente virtual de KIT CONSULTING, especializado en ayudas "
                    "gubernamentales para la transformación digital de empresas.\n\n"
                    "REQUISITOS DE ELEGIBILIDAD ESENCIALES:\n"
                    "1. Número de empleados:\n"
                    "   - Mínimo: 10 empleados\n"
                    "   - Máximo: 249 empleados\n"
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
