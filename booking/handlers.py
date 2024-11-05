import logging
from datetime import datetime
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from .validators import validate_input
from .slots import get_available_slots

logger = logging.getLogger(__name__)

SERVICES = [
    "Inteligencia Artificial",
    "Ventas Digitales",
    "Estrategia y Rendimiento de Negocio"
]

def handle_phone_collection(user_input, session):
    if user_input.lower() == 'saltar':
        user_input = ''
    elif not validate_input('phone', user_input):
        return "Por favor, ingresa un número de teléfono español válido o escribe 'saltar'." + session.format_state_data()
    
    session.data['phone'] = user_input
    session.state = 'SELECTING_SERVICE'
    return handle_service_selection(None, session)

def handle_service_selection(user_input, session):
    if user_input is not None:
        if not validate_input('service', user_input):
            return "Por favor, selecciona un número válido de la lista." + session.format_state_data()
        
        service_index = int(user_input) - 1
        session.data['service'] = f"{SERVICES[service_index]} (hasta 6.000€)"
        session.state = 'SELECTING_DATE'
        
        slots = get_available_slots()
        if not slots:
            return "Lo siento, no hay fechas disponibles en los próximos días." + session.format_state_data()
        
        dates_list = "\n".join([f"{i+1}. {slot['formatted_date']}" for i, slot in enumerate(slots)])
        return (
            f"Has seleccionado: <strong>{session.data['service']}</strong>\n\n"
            "<strong>Estas son las fechas disponibles:</strong>\n" +
            dates_list + "\n\n"
            "<strong>Por favor, selecciona el número de la fecha que prefieres:</strong>" +
            session.format_state_data()
        )
    
    return (
        "<strong>¿Qué servicio te interesa?</strong>\n\n"
        "<br>1. Inteligencia Artificial (hasta 6.000€)\n"
        "<br>2. Ventas Digitales (hasta 6.000€)\n"
        "<br>3. Estrategia y Rendimiento de Negocio (hasta 6.000€)\n\n"
        "<strong>Por favor, selecciona el número del servicio deseado:</strong>" +
        session.format_state_data()
    )

def handle_booking_step(user_input, session):
    """Handle each step of the booking process"""
    try:
        if session.state == 'INITIAL':
            session.state = 'COLLECTING_NAME'
            return (
                "<strong>¡Bienvenido al sistema de reservas!</strong>\n\n"
                "Para ayudarte a agendar una cita, necesito algunos datos.\n\n"
                "<strong>Por favor, introduce tu nombre completo:</strong>" +
                session.format_state_data()
            )
        
        elif session.state == 'COLLECTING_NAME':
            if not validate_input('name', user_input):
                return "Por favor, ingresa un nombre válido usando solo letras." + session.format_state_data()
            
            session.data['name'] = user_input
            session.state = 'COLLECTING_EMAIL'
            return (
                f"Gracias {user_input}.\n\n"
                "<strong>Por favor, introduce tu correo electrónico para enviarte "
                "la confirmación de la cita:</strong>" +
                session.format_state_data()
            )
        
        elif session.state == 'COLLECTING_EMAIL':
            if not validate_input('email', user_input):
                return "Por favor, ingresa un correo electrónico válido." + session.format_state_data()
            
            session.data['email'] = user_input
            session.state = 'COLLECTING_PHONE'
            return (
                "<strong>¿Podrías proporcionarme un número de teléfono para contactarte "
                "en caso necesario?</strong>\n"
                "(Este campo es opcional, puedes escribir 'saltar' para continuar)" +
                session.format_state_data()
            )
        
        elif session.state == 'COLLECTING_PHONE':
            return handle_phone_collection(user_input, session)
        
        elif session.state == 'SELECTING_SERVICE':
            return handle_service_selection(user_input, session)
        
        elif session.state == 'SELECTING_DATE':
            if not validate_input('date', user_input):
                return "Por favor, selecciona un número válido de la lista." + session.format_state_data()
            
            slots = get_available_slots()
            date_index = int(user_input) - 1
            
            if date_index < 0 or date_index >= len(slots):
                return "Por favor, selecciona un número válido de la lista." + session.format_state_data()
            
            selected_date = slots[date_index]
            session.data['date'] = selected_date['date']
            session.data['formatted_date'] = selected_date['formatted_date']
            session.state = 'SELECTING_TIME'
            
            times_list = "\n".join([f"{i+1}. {time}" for i, time in enumerate(selected_date['times'])])
            return (
                f"Has seleccionado el <strong>{selected_date['formatted_date']}</strong>.\n\n"
                "<strong>Estos son los horarios disponibles:</strong>\n" +
                times_list + "\n\n"
                "<strong>Por favor, selecciona el número del horario que prefieres:</strong>" +
                session.format_state_data()
            )
        
        elif session.state == 'SELECTING_TIME':
            slots = get_available_slots()
            selected_slot = next(
                slot for slot in slots 
                if slot['date'] == session.data['date']
            )
            
            time_index = int(user_input) - 1
            if time_index < 0 or time_index >= len(selected_slot['times']):
                return "Por favor, selecciona un número válido de la lista." + session.format_state_data()
            
            session.data['time'] = selected_slot['times'][time_index]
            session.state = 'CONFIRMATION'
            
            return (
                "<strong>Resumen de tu cita:</strong>\n\n"
                f"Nombre: {session.data['name']}\n"
                f"Email: {session.data['email']}\n"
                f"Teléfono: {session.data['phone'] or 'No proporcionado'}\n"
                f"Servicio: {session.data['service']}\n"
                f"Fecha: {session.data['formatted_date']}\n"
                f"Hora: {session.data['time']}\n\n"
                "<strong>¿Los datos son correctos?</strong> (Responde 'sí' para confirmar o 'no' para cancelar)" +
                session.format_state_data()
            )
        
        elif session.state == 'CONFIRMATION':
            if user_input.lower() in ['si', 'sí', 'yes']:
                try:
                    appointment = Appointment(
                        name=session.data['name'],
                        email=session.data['email'],
                        phone=session.data['phone'],
                        date=datetime.strptime(session.data['date'], '%Y-%m-%d').date(),
                        time=session.data['time'],
                        service=session.data['service']
                    )
                    db.session.add(appointment)
                    db.session.commit()
                    
                    send_appointment_confirmation(appointment)
                    schedule_reminder_email(appointment)
                    
                    return (
                        "<strong>¡Tu cita ha sido confirmada!</strong>\n\n"
                        "Te hemos enviado un correo electrónico con los detalles.\n"
                        "También recibirás un recordatorio 24 horas antes de la cita.\n\n"
                        "¿Hay algo más en lo que pueda ayudarte?\n\nBOOKING_COMPLETE"
                    )
                except Exception as e:
                    logger.error(f"Error creating appointment: {str(e)}")
                    return (
                        "<strong>Lo siento, ha ocurrido un error al procesar tu cita.</strong>\n"
                        "Por favor, inténtalo de nuevo más tarde."
                    )
            elif user_input.lower() in ['no']:
                return (
                    "<strong>Entiendo, cancelaremos esta reserva.</strong>\n\n"
                    "¿Te gustaría comenzar una nueva reserva?"
                )
            else:
                return (
                    "Por favor, responde 'sí' para confirmar o 'no' para cancelar." +
                    session.format_state_data()
                )
        
    except Exception as e:
        logger.error(f"Error in booking step: {str(e)}")
        return "Lo siento, ha ocurrido un error. Por favor, inténtalo de nuevo."
