from flask import render_template, current_app
from flask_mail import Mail, Message
from datetime import datetime, timedelta
import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv
import time
from smtplib import SMTPException

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
    """Decorator to retry failed email operations"""
    def wrapper(*args, **kwargs):
        max_retries = 3
        retry_delay = 1  # seconds
        
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == max_retries - 1:
                    logger.error(f"Final attempt failed for {func.__name__}: {str(e)}")
                    raise
                logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}, retrying in {retry_delay}s: {str(e)}")
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
            'contact_email': current_app.config['MAIL_USERNAME'],
            'cancel_url': f"{current_app.config['BASE_URL']}/cancel/{appointment.id}",
            'reschedule_url': f"{current_app.config['BASE_URL']}/reschedule/{appointment.id}"
        }
        
        # Create HTML content
        msg.html = render_template('email/appointment_confirmation.html', **context)
        
        # Attach logo if it exists
        try:
            with current_app.open_resource('static/img/logo.svg') as logo:
                msg.attach('logo.svg', 'image/svg+xml', logo.read(), 'inline', 
                          headers=[('Content-ID', '<logo>')])
        except Exception as e:
            logger.warning(f"Failed to attach logo to email: {str(e)}")
        
        # Send email
        mail.send(msg)
        logger.info(f"Confirmation email sent successfully for appointment {appointment.id}")
        
    except SMTPException as e:
        logger.error(f"SMTP error sending confirmation email for appointment {appointment.id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending confirmation email for appointment {appointment.id}: {str(e)}")
        raise

@retry_on_failure
def send_appointment_reminder(appointment):
    """Send reminder email for an upcoming appointment with enhanced error handling"""
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
            'contact_email': current_app.config['MAIL_USERNAME'],
            'cancel_url': f"{current_app.config['BASE_URL']}/cancel/{appointment.id}",
            'reschedule_url': f"{current_app.config['BASE_URL']}/reschedule/{appointment.id}"
        }
        
        # Create HTML content
        msg.html = render_template('email/appointment_reminder.html', **context)
        
        # Attach logo if it exists
        try:
            with current_app.open_resource('static/img/logo.svg') as logo:
                msg.attach('logo.svg', 'image/svg+xml', logo.read(), 'inline', 
                          headers=[('Content-ID', '<logo>')])
        except Exception as e:
            logger.warning(f"Failed to attach logo to email: {str(e)}")
        
        # Send email
        mail.send(msg)
        logger.info(f"Reminder email sent successfully for appointment {appointment.id}")
        
    except SMTPException as e:
        logger.error(f"SMTP error sending reminder email for appointment {appointment.id}: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error sending reminder email for appointment {appointment.id}: {str(e)}")
        raise

def schedule_reminder_email(appointment):
    """Schedule a reminder email for 24 hours before the appointment with improved logging"""
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
