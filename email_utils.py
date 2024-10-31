from flask import render_template, current_app
from flask_mail import Mail, Message
from datetime import datetime, timedelta
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.date import DateTrigger
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

mail = Mail()
scheduler = BackgroundScheduler()
scheduler.start()

def send_appointment_confirmation(appointment):
    """Send confirmation email for a new appointment"""
    msg = Message(
        f'{os.getenv("APP_NAME", "AI Engineering Consultancy")} - Appointment Confirmation',
        sender=current_app.config['MAIL_USERNAME'],
        recipients=[appointment.email]
    )
    
    # Prepare template context
    context = {
        'name': appointment.name,
        'service': appointment.service,
        'date': appointment.date.strftime('%B %d, %Y'),
        'time': appointment.time,
        'contact_email': current_app.config['MAIL_USERNAME'],
        'cancel_url': f"{current_app.config['BASE_URL']}/cancel/{appointment.id}",
        'reschedule_url': f"{current_app.config['BASE_URL']}/reschedule/{appointment.id}"
    }
    
    # Create HTML content
    msg.html = render_template('email/appointment_confirmation.html', **context)
    
    # Attach logo
    with current_app.open_resource('static/img/logo.svg') as logo:
        msg.attach('logo.svg', 'image/svg+xml', logo.read(), 'inline', headers={'Content-ID': '<logo>'})
    
    mail.send(msg)

def send_appointment_reminder(appointment):
    """Send reminder email for an upcoming appointment"""
    msg = Message(
        f'{os.getenv("APP_NAME", "AI Engineering Consultancy")} - Appointment Reminder',
        sender=current_app.config['MAIL_USERNAME'],
        recipients=[appointment.email]
    )
    
    # Prepare template context
    context = {
        'name': appointment.name,
        'service': appointment.service,
        'date': appointment.date.strftime('%B %d, %Y'),
        'time': appointment.time,
        'contact_email': current_app.config['MAIL_USERNAME'],
        'cancel_url': f"{current_app.config['BASE_URL']}/cancel/{appointment.id}",
        'reschedule_url': f"{current_app.config['BASE_URL']}/reschedule/{appointment.id}"
    }
    
    # Create HTML content
    msg.html = render_template('email/appointment_reminder.html', **context)
    
    # Attach logo
    with current_app.open_resource('static/img/logo.svg') as logo:
        msg.attach('logo.svg', 'image/svg+xml', logo.read(), 'inline', headers={'Content-ID': '<logo>'})
    
    mail.send(msg)

def schedule_reminder_email(appointment):
    """Schedule a reminder email for 24 hours before the appointment"""
    reminder_time = datetime.combine(appointment.date, datetime.strptime(appointment.time, '%H:%M').time()) - timedelta(days=1)
    if reminder_time > datetime.now():
        scheduler.add_job(
            send_appointment_reminder,
            trigger=DateTrigger(run_date=reminder_time),
            args=[appointment],
            id=f'reminder_{appointment.id}'
        )
