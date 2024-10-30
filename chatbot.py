import os
from openai import OpenAI
from datetime import datetime
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email

# Set up logging and OpenAI configuration
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
client = OpenAI(api_key=os.environ.get('OPENAI_API_KEY'))

# Metrics tracking
metrics = {
    "total_queries": 0,
    "successful_queries": 0,
    "response_times": [],
    "daily_stats": {}
}

# KIT CONSULTING Information
COMPANY_INFO = """
Navegatel es una compañía de desarrollo, actualmente tienen la capcidad de asesores digitales por el estado y pueden getionar KIT DIGITAL y la novedad del KIT CONSULTING, que el KIT CONSULTING es un programa de ayudas del Gobierno de España que permite a pymes diseñar la hoja de ruta para su transformación digital.

Servicios principales:
1. Inteligencia Artificial - hasta 6.000€
2. Ventas Digitales - hasta 6.000€
3. Estrategia y Rendimiento de Negocio - hasta 6.000€

Segmentos de empresas:
- Segmento A (10-49 empleados): 12.000€
- Segmento B (50-99 empleados): 18.000€
- Segmento C (100-249 empleados): 24.000€

Requisitos básicos:
- Tener domicilio fiscal en territorio español
- Ser pequeña o mediana empresa
- Estar inscrito en el censo de empresarios
- No tener consideración de empresa en crisis
- Estar al corriente de obligaciones tributarias
"""

def get_chat_response(user_message, conversation_history=None):
    """Generate a response using OpenAI's ChatGPT"""
    try:
        if conversation_history is None:
            conversation_history = []

        # Prepare the conversation with system context
        messages = [
            {
                "role": "system",
                "content": f"Eres un asistente virtual de Navegatel especializado en el KIT CONSULTING. Tu objetivo es ayudar a los usuarios a entender el programa de ayudas y guiarlos en el proceso de solicitud. IMPORTANTE ofrecerles nuestros servicios y que agenden una cita. COMPORTAMIENTO se muy amigable, haz resupuestas faciles de leer pero no dejes de ser profesional. Aquí está la información clave sobre KIT CONSULTING: {COMPANY_INFO}"
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            messages.append({"role": "user" if msg["is_user"] else "assistant", "content": msg["text"]})

        # Add the current message
        messages.append({"role": "user", "content": user_message})

        # Get response from OpenAI using the new API
        response = client.chat.completions.create(
            model="gpt-4",
            messages=messages,
            max_tokens=500,
            temperature=0.7,
            top_p=0.9
        )

        return response.choices[0].message.content

    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        return "Lo siento, ha ocurrido un error. ¿Podrías intentarlo de nuevo?"

def get_model_metrics():
    """Get current performance metrics"""
    if not metrics["response_times"]:
        return {
            "avg_response_time": 0,
            "success_rate": 0,
            "daily_queries": 0
        }
    
    avg_response_time = sum(metrics["response_times"]) / len(metrics["response_times"])
    success_rate = (metrics["successful_queries"] / metrics["total_queries"]) * 100 if metrics["total_queries"] > 0 else 0
    
    today = datetime.now().strftime("%Y-%m-%d")
    daily_queries = metrics["daily_stats"].get(today, {}).get("queries", 0)
    
    return {
        "avg_response_time": round(avg_response_time, 2),
        "success_rate": round(success_rate, 2),
        "daily_queries": daily_queries
    }

def update_metrics(start_time, success):
    """Update performance metrics"""
    end_time = datetime.now()
    response_time = (end_time - start_time).total_seconds() * 1000
    
    metrics["total_queries"] += 1
    if success:
        metrics["successful_queries"] += 1
    metrics["response_times"].append(response_time)
    
    today = end_time.strftime("%Y-%m-%d")
    if today not in metrics["daily_stats"]:
        metrics["daily_stats"][today] = {
            "queries": 0,
            "successful": 0,
            "avg_response_time": 0
        }
    
    daily_stats = metrics["daily_stats"][today]
    daily_stats["queries"] += 1
    if success:
        daily_stats["successful"] += 1
    daily_stats["avg_response_time"] = (
        (daily_stats["avg_response_time"] * (daily_stats["queries"] - 1) + response_time)
        / daily_stats["queries"]
    )

def generate_response(message, conversation_history=None):
    """Generate chatbot response"""
    start_time = datetime.now()
    try:
        response = get_chat_response(message, conversation_history)
        update_metrics(start_time, True)
        return response
        
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        update_metrics(start_time, False)
        return "Lo siento, ha ocurrido un error. ¿Podrías intentarlo de nuevo?"
