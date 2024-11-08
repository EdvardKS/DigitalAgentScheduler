from flask import render_template, current_app
from flask_mail import Mail, Message
from datetime import datetime, timedelta
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv
import time
from smtplib import SMTPException, SMTPAuthenticationError, SMTPServerDisconnected

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

mail = Mail()
scheduler = BackgroundScheduler()
scheduler.start()

def retry_on_failure(func):
    """Decorator to retry failed email operations with enhanced error handling"""
    def wrapper(*args, **kwargs):
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except SMTPAuthenticationError as e:
                logger.error(f"SMTP Authentication Error: {str(e)}")
                logger.error("Please verify your email credentials")
                raise
            except SMTPServerDisconnected as e:
                if attempt == max_retries - 1:
                    logger.error(f"SMTP Server Disconnected: {str(e)}")
                    raise
                logger.warning(f"Server disconnected, attempting to reconnect... (Attempt {attempt + 1})")
                time.sleep(retry_delay)
            except SMTPException as e:
                if attempt == max_retries - 1:
                    logger.error(f"SMTP Error: {str(e)}")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed, retrying in {retry_delay}s: {str(e)}")
                time.sleep(retry_delay)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Unexpected error: {str(e)}")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed, retrying in {retry_delay}s: {str(e)}")
                time.sleep(retry_delay)
            retry_delay *= 2
    return wrapper

@retry_on_failure
def send_appointment_confirmation(appointment):
    """Send confirmation email for a new appointment with enhanced error handling"""
    try:
        logger.info(f"Preparing confirmation email for appointment {appointment.id}")
        
        msg = Message(
            f'{os.getenv("APP_NAME", "KIT CONSULTING")} - Confirmación de Cita',
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[appointment.email]
        )
        
        # Prepare template context
        context = {
            'name': appointment.name,
            'service': appointment.service,
            'date': appointment.date.strftime('%d de %B de %Y'),
            'time': appointment.time,
            'email': appointment.email,
            'phone': getattr(appointment, 'phone', None),
            'contact_email': current_app.config['MAIL_USERNAME'],
            'cancel_url': f"{current_app.config['BASE_URL']}/cancel/{appointment.id}",
            'reschedule_url': f"{current_app.config['BASE_URL']}/reschedule/{appointment.id}"
        }
        
        # Create HTML content
        msg.html = render_template('email/appointment_confirmation.html', **context)
        
        # Attach logo if it exists
        try:
            with current_app.open_resource('static/disenyo/SVG/01-LOGO.svg') as logo:
                msg.attach('logo.svg', 'image/svg+xml', logo.read(), 'inline', 
                          headers=[('Content-ID', '<logo>')])
        except Exception as e:
            logger.warning(f"Failed to attach logo to email: {str(e)}")
        
        # Send email
        mail.send(msg)
        logger.info(f"Confirmation email sent successfully for appointment {appointment.id}")
        
    except Exception as e:
        logger.error(f"Error sending confirmation email for appointment {appointment.id}: {str(e)}")
        raise

@retry_on_failure
def send_contact_form_notification(form_data):
    """Send notification email for contact form submission"""
    try:
        logger.info("Preparing contact form notification email")
        
        # Create message for admin
        admin_msg = Message(
            f'{os.getenv("APP_NAME", "KIT CONSULTING")} - Nueva Consulta',
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[current_app.config['MAIL_USERNAME']]  # Send to admin
        )
        
        # Create message for user
        user_msg = Message(
            f'{os.getenv("APP_NAME", "KIT CONSULTING")} - Hemos recibido tu consulta',
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[form_data['email']]
        )
        
        # Prepare template context
        context = {
            'nombre': form_data['nombre'],
            'email': form_data['email'],
            'telefono': form_data['telefono'],
            'dudas': form_data['dudas']
        }
        
        # Create HTML content
        admin_msg.html = render_template('email/contact_form.html', **context)
        user_msg.html = render_template('email/contact_form_confirmation.html', **context)
        
        # Attach logo to both emails
        try:
            with current_app.open_resource('static/disenyo/SVG/01-LOGO.svg') as logo:
                logo_data = logo.read()
                for msg in [admin_msg, user_msg]:
                    msg.attach('logo.svg', 'image/svg+xml', logo_data, 'inline',
                             headers=[('Content-ID', '<logo>')])
        except Exception as e:
            logger.warning(f"Failed to attach logo to email: {str(e)}")
        
        # Send emails
        mail.send(admin_msg)
        mail.send(user_msg)
        logger.info("Contact form notification emails sent successfully")
        
    except Exception as e:
        logger.error(f"Error sending contact form notification: {str(e)}")
        raise

@retry_on_failure
def send_appointment_reminder(appointment):
    """Send reminder email for an upcoming appointment"""
    try:
        logger.info(f"Preparing reminder email for appointment {appointment.id}")
        
        msg = Message(
            f'{os.getenv("APP_NAME", "KIT CONSULTING")} - Recordatorio de Cita',
            sender=current_app.config['MAIL_USERNAME'],
            recipients=[appointment.email]
        )
        
        # Prepare template context
        context = {
            'name': appointment.name,
            'service': appointment.service,
            'date': appointment.date.strftime('%d de %B de %Y'),
            'time': appointment.time,
            'email': appointment.email,
            'phone': getattr(appointment, 'phone', None),
            'contact_email': current_app.config['MAIL_USERNAME'],
            'cancel_url': f"{current_app.config['BASE_URL']}/cancel/{appointment.id}",
            'reschedule_url': f"{current_app.config['BASE_URL']}/reschedule/{appointment.id}"
        }
        
        # Create HTML content
        msg.html = render_template('email/appointment_reminder.html', **context)
        
        # Attach logo if it exists
        try:
            with current_app.open_resource('static/disenyo/SVG/01-LOGO.svg') as logo:
                msg.attach('logo.svg', 'image/svg+xml', logo.read(), 'inline', 
                          headers=[('Content-ID', '<logo>')])
        except Exception as e:
            logger.warning(f"Failed to attach logo to email: {str(e)}")
        
        # Send email
        mail.send(msg)
        logger.info(f"Reminder email sent successfully for appointment {appointment.id}")
        
    except Exception as e:
        logger.error(f"Error sending reminder email for appointment {appointment.id}: {str(e)}")
        raise

def schedule_reminder_email(appointment):
    """Schedule a reminder email for 24 hours before the appointment"""
    try:
        reminder_time = datetime.combine(appointment.date, 
                                       datetime.strptime(appointment.time, '%H:%M').time()) - timedelta(days=1)
        
        if reminder_time > datetime.now():
            scheduler.add_job(
                send_appointment_reminder,
                trigger=DateTrigger(run_date=reminder_time),
                args=[appointment],
                id=f'reminder_{appointment.id}',
                replace_existing=True
            )
            logger.info(f"Scheduled reminder email for appointment {appointment.id} at {reminder_time}")
        else:
            logger.warning(f"Skipped scheduling reminder for past appointment {appointment.id}")
            
    except Exception as e:
        logger.error(f"Error scheduling reminder email for appointment {appointment.id}: {str(e)}")
        raise
