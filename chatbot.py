import os
import openai
from datetime import datetime, timedelta
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from dotenv import load_dotenv
import json
import re

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

# Company Information
COMPANY_INFO = """
Somos Navegatel, una empresa especializada en asesoría digital, expertos en el programa KIT CONSULTING. El KIT CONSULTING es un programa de ayudas del Gobierno de España que permite a pymes diseñar la hoja de ruta para su transformación digital.

Servicios principales:
1. Inteligencia Artificial - hasta 6.000€
2. Ventas Digitales - hasta 6.000€
3. Estrategia y Rendimiento de Negocio - hasta 6.000€

Segmentos de empresas:
- Segmento A (10-49 empleados): 12.000€
- Segmento B (50-99 empleados): 18.000€
- Segmento C (100-249 empleados): 24.000€

Horario de atención para citas:
- Lunes a Viernes
- 10:30 AM a 2:00 PM

Requisitos básicos:
- Tener domicilio fiscal en territorio español
- Ser pequeña o mediana empresa
- Estar inscrito en el censo de empresarios
- No tener consideración de empresa en crisis
- Estar al corriente de obligaciones tributarias

IMPORTANTE:
- Responde solo ha preguntas relacionadas con el KIT CONSULTING o servicios de Navegatel.
- Somos especialistas en Inteligencia Artificial, Ventas Digitales y Estrategia y Rendimiento de Negocio.
- Si el usuario quiere agendar una cita, ayúdale a completar el proceso pidiendo la información necesaria.
- Para contacto directo: info@navegatel.org o 673 66 09 10
"""

FALLBACK_RESPONSES = [
    "Lo siento, estamos experimentando dificultades técnicas. Por favor, intenta de nuevo en unos momentos.",
    "Disculpa la interrupción. ¿Podrías reformular tu pregunta?",
    "En este momento no puedo procesar tu solicitud. Para asistencia inmediata, contáctanos en info@navegatel.org o 673 66 09 10.",
]

def extract_appointment_info(message):
    """Extract appointment information from user message"""
    appointment_info = {}
    
    # Extract email using regex
    email_pattern = r'[\w\.-]+@[\w\.-]+\.\w+'
    email_match = re.search(email_pattern, message)
    if email_match:
        appointment_info['email'] = email_match.group()
    
    # Extract date using common formats
    date_patterns = [
        r'\d{4}-\d{2}-\d{2}',  # YYYY-MM-DD
        r'\d{2}/\d{2}/\d{4}',  # DD/MM/YYYY
        r'\d{2}-\d{2}-\d{4}'   # DD-MM-YYYY
    ]
    
    for pattern in date_patterns:
        date_match = re.search(pattern, message)
        if date_match:
            try:
                date_str = date_match.group()
                if '/' in date_str:
                    date = datetime.strptime(date_str, '%d/%m/%Y').strftime('%Y-%m-%d')
                else:
                    date = datetime.strptime(date_str, '%Y-%m-%d').strftime('%Y-%m-%d')
                appointment_info['date'] = date
                break
            except ValueError:
                continue
    
    # Extract time using 24-hour format
    time_pattern = r'([01]?[0-9]|2[0-3]):[0-5][0-9]'
    time_match = re.search(time_pattern, message)
    if time_match:
        appointment_info['time'] = time_match.group()
    
    # Extract service
    services = ['Inteligencia Artificial', 'Ventas Digitales', 'Estrategia y Rendimiento']
    for service in services:
        if service.lower() in message.lower():
            appointment_info['service'] = service
            break
    
    # Extract name (assuming it's at the beginning of the message or after "me llamo" or "soy")
    name_patterns = [
        r'me llamo ([A-Za-zÁáÉéÍíÓóÚúÑñ\s]+)',
        r'soy ([A-Za-zÁáÉéÍíÓóÚúÑñ\s]+)',
        r'^([A-Za-zÁáÉéÍíÓóÚúÑñ\s]+)'
    ]
    
    for pattern in name_patterns:
        name_match = re.search(pattern, message, re.IGNORECASE)
        if name_match:
            name = name_match.group(1).strip()
            if len(name) > 2:  # Avoid single letters or very short strings
                appointment_info['name'] = name
                break
    
    return appointment_info

def get_fallback_response():
    """Get a random fallback response"""
    from random import choice
    return choice(FALLBACK_RESPONSES)

def get_chat_response(user_message, conversation_history=None):
    """Generate a response using OpenAI's ChatGPT with enhanced error handling"""
    try:
        logger.info(f"Processing chat request - Message length: {len(user_message)}")
        
        if not user_message.strip():
            logger.warning("Empty message received")
            return "Por favor, escribe tu pregunta para poder ayudarte."

        if conversation_history is None:
            conversation_history = []

        # Check if message contains appointment-related keywords
        appointment_keywords = ['cita', 'agendar', 'reservar', 'appointment', 'consulta']
        is_appointment_request = any(keyword in user_message.lower() for keyword in appointment_keywords)

        # Extract appointment information if it's an appointment request
        appointment_info = {}
        if is_appointment_request:
            appointment_info = extract_appointment_info(user_message)

        # Prepare the conversation with system context
        messages = [
            {
                "role": "system",
                "content": f"""Eres el asistente virtual de Navegatel, especializado en el programa KIT CONSULTING. 
                Tu objetivo es ayudar a los usuarios a entender el programa de ayudas y guiarlos en el proceso de solicitud.
                
                Si el usuario quiere agendar una cita, ayúdale a completar el proceso pidiendo la información necesaria:
                - Nombre completo
                - Email
                - Servicio de interés (IA, Ventas Digitales, o Estrategia)
                - Fecha preferida (L-V, 10:30-14:00)
                
                Información importante: {COMPANY_INFO}
                
                Appointment Info Detected: {json.dumps(appointment_info, ensure_ascii=False)}"""
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            messages.append({"role": "user" if msg["is_user"] else "assistant", "content": msg["text"]})

        # Add the current message
        messages.append({"role": "user", "content": user_message})

        # Get response from OpenAI with timeout handling
        try:
            response = openai.ChatCompletion.create(
                model="ft:gpt-4o-2024-08-06:personal::AO1TjiAT",
                messages=messages,
                max_tokens=500,
                temperature=0.7,
                top_p=0.9,
                presence_penalty=0.6,
                frequency_penalty=0.3,
                request_timeout=30
            )
            logger.info("Successfully received response from OpenAI")
            return response.choices[0].message["content"]

        except openai.error.Timeout:
            logger.error("OpenAI API request timed out")
            return "Lo siento, la respuesta está tardando más de lo esperado. Por favor, intenta de nuevo."
        
        except openai.error.APIError as e:
            logger.error(f"OpenAI API error: {str(e)}")
            return get_fallback_response()
        
        except openai.error.RateLimitError:
            logger.error("OpenAI API rate limit exceeded")
            return "Estamos experimentando un alto volumen de consultas. Por favor, intenta de nuevo en unos minutos."

    except Exception as e:
        logger.error(f"Unexpected error in get_chat_response: {str(e)}", exc_info=True)
        metrics["error_types"][type(e).__name__] = metrics["error_types"].get(type(e).__name__, 0) + 1
        return get_fallback_response()

def get_model_metrics():
    """Get current performance metrics with enhanced error tracking"""
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
        
        # Get top 3 most common errors
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

def update_metrics(start_time, success):
    """Update performance metrics with error tracking"""
    try:
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
    except Exception as e:
        logger.error(f"Error updating metrics: {str(e)}", exc_info=True)

def generate_response(message, conversation_history=None):
    """Generate chatbot response with comprehensive error handling"""
    start_time = datetime.now()
    success = False
    
    try:
        if not message.strip():
            logger.warning("Empty message received in generate_response")
            return "Por favor, escribe tu pregunta para poder ayudarte."
            
        response = get_chat_response(message, conversation_history)
        success = True
        return response
        
    except Exception as e:
        logger.error(f"Error in generate_response: {str(e)}", exc_info=True)
        metrics["error_types"][type(e).__name__] = metrics["error_types"].get(type(e).__name__, 0) + 1
        return get_fallback_response()
    
    finally:
        update_metrics(start_time, success)
