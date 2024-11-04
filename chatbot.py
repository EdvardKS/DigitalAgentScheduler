import os
import openai
from datetime import datetime, timedelta
import logging
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from dotenv import load_dotenv
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

# Appointment booking states
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

# Available services
SERVICES = [
    "Inteligencia Artificial (hasta 6.000€)",
    "Ventas Digitales (hasta 6.000€)",
    "Estrategia y Rendimiento de Negocio (hasta 6.000€)"
]

# Navegatel and KIT CONSULTING Information
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

Requisitos básicos:
- Tener domicilio fiscal en territorio español
- Ser pequeña o mediana empresa
- Estar inscrito en el censo de empresarios
- No tener consideración de empresa en crisis
- Estar al corriente de obligaciones tributarias
"""

def validate_name(name):
    """Validate that name contains only letters and spaces"""
    return bool(re.match("^[A-Za-zÀ-ÿ\s]{2,100}$", name))

def validate_email(email):
    """Validate email format"""
    return bool(re.match(r"[^@]+@[^@]+\.[^@]+", email))

def validate_phone(phone):
    """Validate Spanish phone number format"""
    return bool(re.match(r"^(?:\+34|0034|34)?[6789]\d{8}$", phone))

def get_available_slots():
    """Get available appointment slots for next 7 business days"""
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

def get_chat_response(user_message, conversation_history=None):
    """Generate a response using OpenAI's ChatGPT with enhanced booking flow"""
    try:
        if not user_message.strip():
            return "Por favor, escribe tu pregunta para poder ayudarte."

        # Initialize conversation if needed
        if conversation_history is None:
            conversation_history = []

        # Get current booking state
        current_state = 'INITIAL'
        booking_data = {}
        
        for msg in conversation_history:
            if not msg.get('is_user', True):
                if 'BOOKING_STATE:' in msg['text']:
                    current_state = msg['text'].split('BOOKING_STATE:')[1].strip()
                if 'BOOKING_DATA:' in msg['text']:
                    # Parse booking data from conversation
                    data_str = msg['text'].split('BOOKING_DATA:')[1].strip()
                    try:
                        import json
                        booking_data = json.loads(data_str)
                    except:
                        booking_data = {}

        # Handle appointment booking flow
        if current_state != 'INITIAL' or 'cita' in user_message.lower():
            return handle_booking_flow(user_message, current_state, booking_data)

        # Regular chatbot response for non-booking queries
        messages = [
            {
                "role": "system",
                "content": f"Eres el asistente virtual de Navegatel, especializado en el programa KIT CONSULTING. "
                          f"Tu objetivo es ayudar a los usuarios a entender el programa de ayudas y guiarlos en el proceso de solicitud. "
                          f"Aquí está la información clave: {COMPANY_INFO}"
                          f"Si el usuario muestra interés en los servicios, especialmente en IA, sugiérele agendar una cita."
            }
        ]

        # Add conversation history
        for msg in conversation_history:
            if 'BOOKING_STATE:' not in msg['text'] and 'BOOKING_DATA:' not in msg['text']:
                messages.append({"role": "user" if msg["is_user"] else "assistant", "content": msg["text"]})

        # Add the current message
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

def handle_booking_flow(user_input, current_state, booking_data):
    """Handle the step-by-step booking flow"""
    
    if current_state == 'INITIAL':
        return (
            "¡Excelente elección! La Inteligencia Artificial es un servicio muy potente para la transformación digital de tu "
            "empresa. Para agendar una cita, necesito algunos datos. Por favor, proporcióneme tu nombre.\n\n"
            "BOOKING_STATE:COLLECTING_NAME\n"
            "BOOKING_DATA:{}"
        )
    
    elif current_state == 'COLLECTING_NAME':
        if not validate_name(user_input):
            return (
                "El nombre proporcionado no parece válido. Por favor, ingresa tu nombre completo usando solo letras.\n\n"
                f"BOOKING_STATE:COLLECTING_NAME\n"
                f"BOOKING_DATA:{booking_data}"
            )
        
        booking_data['name'] = user_input
        return (
            "Gracias. Ahora necesito tu correo electrónico para enviarte la confirmación de la cita.\n\n"
            f"BOOKING_STATE:COLLECTING_EMAIL\n"
            f"BOOKING_DATA:{booking_data}"
        )
    
    elif current_state == 'COLLECTING_EMAIL':
        if not validate_email(user_input):
            return (
                "El correo electrónico no parece válido. Por favor, ingresa una dirección de correo válida.\n\n"
                f"BOOKING_STATE:COLLECTING_EMAIL\n"
                f"BOOKING_DATA:{booking_data}"
            )
        
        booking_data['email'] = user_input
        return (
            "Perfecto. Ahora necesito tu número de teléfono para contactarte si es necesario.\n\n"
            f"BOOKING_STATE:COLLECTING_PHONE\n"
            f"BOOKING_DATA:{booking_data}"
        )
    
    elif current_state == 'COLLECTING_PHONE':
        if not validate_phone(user_input):
            return (
                "El número de teléfono no parece válido. Por favor, ingresa un número de teléfono español válido.\n\n"
                f"BOOKING_STATE:COLLECTING_PHONE\n"
                f"BOOKING_DATA:{booking_data}"
            )
        
        booking_data['phone'] = user_input
        services_text = "\n".join(f"{i+1}. {service}" for i, service in enumerate(SERVICES))
        return (
            f"Gracias. ¿Qué servicio te interesa? Por favor, selecciona el número correspondiente:\n\n{services_text}\n\n"
            f"BOOKING_STATE:SELECTING_SERVICE\n"
            f"BOOKING_DATA:{booking_data}"
        )
    
    elif current_state == 'SELECTING_SERVICE':
        try:
            service_index = int(user_input) - 1
            if 0 <= service_index < len(SERVICES):
                booking_data['service'] = SERVICES[service_index]
                slots = get_available_slots()
                dates_text = "\n".join(f"{i+1}. {slot['date']}" for i, slot in enumerate(slots))
                return (
                    f"Excelente elección. Estos son los días disponibles:\n\n{dates_text}\n\n"
                    f"Por favor, selecciona el número del día que prefieres.\n\n"
                    f"BOOKING_STATE:SELECTING_DATE\n"
                    f"BOOKING_DATA:{booking_data}"
                )
        except:
            pass
        
        return (
            "Por favor, selecciona un número válido del 1 al 3 para elegir el servicio.\n\n"
            f"BOOKING_STATE:SELECTING_SERVICE\n"
            f"BOOKING_DATA:{booking_data}"
        )
    
    elif current_state == 'SELECTING_DATE':
        try:
            slots = get_available_slots()
            date_index = int(user_input) - 1
            if 0 <= date_index < len(slots):
                selected_date = slots[date_index]
                booking_data['date'] = selected_date['date']
                times_text = "\n".join(f"{i+1}. {time}" for i, time in enumerate(selected_date['times']))
                return (
                    f"Perfecto. Estos son los horarios disponibles para el {selected_date['date']}:\n\n{times_text}\n\n"
                    f"Por favor, selecciona el número del horario que prefieres.\n\n"
                    f"BOOKING_STATE:SELECTING_TIME\n"
                    f"BOOKING_DATA:{booking_data}"
                )
        except:
            pass
        
        return (
            "Por favor, selecciona un número válido para la fecha.\n\n"
            f"BOOKING_STATE:SELECTING_DATE\n"
            f"BOOKING_DATA:{booking_data}"
        )
    
    elif current_state == 'SELECTING_TIME':
        try:
            slots = get_available_slots()
            selected_slot = next((slot for slot in slots if slot['date'] == booking_data['date']), None)
            if selected_slot:
                time_index = int(user_input) - 1
                if 0 <= time_index < len(selected_slot['times']):
                    booking_data['time'] = selected_slot['times'][time_index]
                    return (
                        f"¡Perfecto! Resumen de tu cita:\n\n"
                        f"Nombre: {booking_data['name']}\n"
                        f"Email: {booking_data['email']}\n"
                        f"Teléfono: {booking_data['phone']}\n"
                        f"Servicio: {booking_data['service']}\n"
                        f"Fecha: {booking_data['date']}\n"
                        f"Hora: {booking_data['time']}\n\n"
                        f"¿Confirmas esta cita? (Responde 'sí' para confirmar o 'no' para cancelar)\n\n"
                        f"BOOKING_STATE:CONFIRMATION\n"
                        f"BOOKING_DATA:{booking_data}"
                    )
        except:
            pass
        
        return (
            "Por favor, selecciona un número válido para el horario.\n\n"
            f"BOOKING_STATE:SELECTING_TIME\n"
            f"BOOKING_DATA:{booking_data}"
        )
    
    elif current_state == 'CONFIRMATION':
        if user_input.lower() in ['si', 'sí', 'yes']:
            try:
                # Create appointment in database
                appointment = Appointment(
                    name=booking_data['name'],
                    email=booking_data['email'],
                    date=datetime.strptime(booking_data['date'], '%Y-%m-%d').date(),
                    time=booking_data['time'],
                    service=booking_data['service']
                )
                db.session.add(appointment)
                db.session.commit()
                
                # Send confirmation email
                send_appointment_confirmation(appointment)
                schedule_reminder_email(appointment)
                
                return (
                    "¡Tu cita ha sido confirmada! Te hemos enviado un correo electrónico con los detalles. "
                    "¿Hay algo más en lo que pueda ayudarte?\n\n"
                    "BOOKING_STATE:INITIAL\n"
                    "BOOKING_DATA:{}"
                )
            except Exception as e:
                logger.error(f"Error creating appointment: {str(e)}")
                return (
                    "Lo siento, ha ocurrido un error al procesar tu cita. Por favor, intenta de nuevo más tarde.\n\n"
                    "BOOKING_STATE:INITIAL\n"
                    "BOOKING_DATA:{}"
                )
        elif user_input.lower() in ['no', 'cancel', 'cancelar']:
            return (
                "De acuerdo, he cancelado la reserva. ¿Hay algo más en lo que pueda ayudarte?\n\n"
                "BOOKING_STATE:INITIAL\n"
                "BOOKING_DATA:{}"
            )
        else:
            return (
                "Por favor, responde 'sí' para confirmar la cita o 'no' para cancelarla.\n\n"
                f"BOOKING_STATE:CONFIRMATION\n"
                f"BOOKING_DATA:{booking_data}"
            )
    
    return "Lo siento, ha ocurrido un error. Por favor, intenta de nuevo."

def generate_response(message, conversation_history=None):
    """Generate chatbot response with comprehensive error handling"""
    start_time = datetime.now()
    success = False
    
    try:
        if not message.strip():
            return "Por favor, escribe tu pregunta para poder ayudarte."
            
        response = get_chat_response(message, conversation_history)
        success = True
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
