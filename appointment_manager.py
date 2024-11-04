from datetime import datetime, time, timedelta
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from sqlalchemy import func
import logging
from flask_mail import Message
from flask import current_app

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AppointmentManager:
    WORKING_HOURS = {
        'start': time(9, 30),
        'end': time(14, 0)
    }
    SLOT_DURATION = 30  # minutes
    TIMEZONE = 'Europe/Madrid'  # Timezone for Elche, Alicante

    @staticmethod
    def create_appointment(name, email, service, date, time_str):
        """Create a new appointment and send confirmation email"""
        try:
            # Validate time slot
            appointment_time = datetime.strptime(time_str, '%H:%M').time()
            if not AppointmentManager.is_valid_time(appointment_time):
                raise ValueError("The selected time is outside working hours (9:30-14:00)")

            # Create appointment instance
            appointment = Appointment(
                name=name,
                email=email,
                service=service,
                date=datetime.strptime(date, '%Y-%m-%d').date(),
                time=time_str,
                status='pending'
            )
            
            # Add to database
            db.session.add(appointment)
            db.session.commit()
            
            # Send confirmation emails
            AppointmentManager.send_appointment_notifications(appointment, 'created')
            schedule_reminder_email(appointment)
            
            logger.info(f"Appointment created successfully for {name} on {date} at {time_str}")
            return appointment
            
        except Exception as e:
            logger.error(f"Error creating appointment: {str(e)}")
            db.session.rollback()
            raise

    @staticmethod
    def update_appointment_status(appointment_id, new_status):
        """Update appointment status and send notifications"""
        try:
            appointment = Appointment.query.get(appointment_id)
            if not appointment:
                raise ValueError(f"Appointment {appointment_id} not found")

            old_status = appointment.status
            appointment.status = new_status
            appointment.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            # Send status update notifications
            AppointmentManager.send_appointment_notifications(appointment, 'status_update', old_status)
            
            logger.info(f"Appointment {appointment_id} status updated to {new_status}")
            return appointment

        except Exception as e:
            logger.error(f"Error updating appointment status: {str(e)}")
            db.session.rollback()
            raise

    @staticmethod
    def send_appointment_notifications(appointment, notification_type, old_status=None):
        """Send notifications about appointment changes"""
        try:
            # Send to client
            client_msg = Message(
                subject=f'KIT CONSULTING - Actualización de Cita',
                sender=current_app.config['MAIL_USERNAME'],
                recipients=[appointment.email]
            )

            # Send to admin
            admin_msg = Message(
                subject=f'KIT CONSULTING - Nueva Actualización de Cita',
                sender=current_app.config['MAIL_USERNAME'],
                recipients=['info@navegatel.org']
            )

            if notification_type == 'created':
                template = 'email/appointment_confirmation.html'
            elif notification_type == 'status_update':
                template = 'email/appointment_status_update.html'

            context = {
                'name': appointment.name,
                'service': appointment.service,
                'date': appointment.date.strftime('%d/%m/%Y'),
                'time': appointment.time,
                'status': appointment.status,
                'old_status': old_status,
                'contact_email': current_app.config['MAIL_USERNAME']
            }

            client_msg.html = render_template(template, **context)
            admin_msg.html = render_template(template, **context, is_admin=True)

            mail = current_app.extensions['mail']
            mail.send(client_msg)
            mail.send(admin_msg)

        except Exception as e:
            logger.error(f"Error sending appointment notifications: {str(e)}")
            raise

    @staticmethod
    def is_valid_time(check_time):
        """Check if time is within working hours"""
        return AppointmentManager.WORKING_HOURS['start'] <= check_time <= AppointmentManager.WORKING_HOURS['end']

    @staticmethod
    def get_available_slots(date_str):
        """Get available appointment slots for a given date"""
        try:
            # Convert string to date
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Generate all possible slots
            slots = []
            current_time = datetime.combine(date, AppointmentManager.WORKING_HOURS['start'])
            end_datetime = datetime.combine(date, AppointmentManager.WORKING_HOURS['end'])
            
            while current_time <= end_datetime:
                slots.append(current_time.strftime('%H:%M'))
                current_time += timedelta(minutes=AppointmentManager.SLOT_DURATION)
            
            # Get booked slots
            booked_appointments = Appointment.query.filter_by(
                date=date
            ).filter(
                Appointment.status != 'cancelled'
            ).all()
            booked_times = {appointment.time for appointment in booked_appointments}
            
            # Return available slots
            available_slots = [slot for slot in slots if slot not in booked_times]
            return available_slots

        except Exception as e:
            logger.error(f"Error getting available slots for {date_str}: {str(e)}")
            raise

    @staticmethod
    def get_next_available_dates(days=7):
        """Get next available business days in Elche, Alicante"""
        available_dates = []
        current_date = datetime.now().date()
        
        while len(available_dates) < days:
            if current_date.weekday() < 5:  # Monday = 0, Friday = 4
                available_dates.append(current_date)
            current_date += timedelta(days=1)
            
        return available_dates

    @staticmethod
    def get_appointments_by_status(status=None):
        """Get appointments filtered by status"""
        try:
            query = Appointment.query
            if status:
                query = query.filter_by(status=status)
            return query.order_by(Appointment.date, Appointment.time).all()
        except Exception as e:
            logger.error(f"Error retrieving appointments by status: {str(e)}")
            return []

    @staticmethod
    def get_appointments_by_date_range(start_date, end_date, status=None):
        """Get appointments within a date range and optionally filtered by status"""
        try:
            query = Appointment.query.filter(
                Appointment.date.between(start_date, end_date)
            )
            if status:
                query = query.filter_by(status=status)
            return query.order_by(Appointment.date, Appointment.time).all()
        except Exception as e:
            logger.error(f"Error retrieving appointments in date range: {str(e)}")
            return []
