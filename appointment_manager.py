from datetime import datetime, time, timedelta
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
from sqlalchemy import func
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AppointmentManager:
    @staticmethod
    def create_appointment(name, email, service, date, time_str):
        """Create a new appointment and send confirmation email"""
        try:
            # Create appointment instance
            appointment = Appointment(
                name=name,
                email=email,
                service=service,
                date=datetime.strptime(date, '%Y-%m-%d').date(),
                time=time_str
            )
            
            # Add to database
            db.session.add(appointment)
            db.session.commit()
            
            # Send confirmation email and schedule reminder
            send_appointment_confirmation(appointment)
            schedule_reminder_email(appointment)
            
            logger.info(f"Appointment created successfully for {name} on {date} at {time_str}")
            return appointment
            
        except Exception as e:
            logger.error(f"Error creating appointment: {str(e)}")
            db.session.rollback()
            raise

    @staticmethod
    def get_appointment(appointment_id):
        """Retrieve an appointment by ID"""
        try:
            return Appointment.query.get(appointment_id)
        except Exception as e:
            logger.error(f"Error retrieving appointment {appointment_id}: {str(e)}")
            return None

    @staticmethod
    def update_appointment(appointment_id, **kwargs):
        """Update an existing appointment"""
        try:
            appointment = Appointment.query.get(appointment_id)
            if not appointment:
                logger.error(f"Appointment {appointment_id} not found")
                return None

            # Update fields
            for key, value in kwargs.items():
                if hasattr(appointment, key):
                    setattr(appointment, key, value)

            db.session.commit()
            logger.info(f"Appointment {appointment_id} updated successfully")
            return appointment

        except Exception as e:
            logger.error(f"Error updating appointment {appointment_id}: {str(e)}")
            db.session.rollback()
            raise

    @staticmethod
    def delete_appointment(appointment_id):
        """Delete an appointment"""
        try:
            appointment = Appointment.query.get(appointment_id)
            if appointment:
                db.session.delete(appointment)
                db.session.commit()
                logger.info(f"Appointment {appointment_id} deleted successfully")
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting appointment {appointment_id}: {str(e)}")
            db.session.rollback()
            raise

    @staticmethod
    def get_available_slots(date_str):
        """Get available appointment slots for a given date"""
        try:
            # Convert string to date
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            # Define business hours (10:30 AM to 2:00 PM)
            start_time = time(10, 30)
            end_time = time(14, 0)
            slot_duration = timedelta(minutes=30)
            
            # Generate all possible slots
            slots = []
            current_time = datetime.combine(date, start_time)
            end_datetime = datetime.combine(date, end_time)
            
            while current_time <= end_datetime:
                slots.append(current_time.strftime('%H:%M'))
                current_time += slot_duration
            
            # Get booked slots
            booked_appointments = Appointment.query.filter_by(date=date).all()
            booked_times = {appointment.time for appointment in booked_appointments}
            
            # Return available slots
            available_slots = [slot for slot in slots if slot not in booked_times]
            return available_slots

        except Exception as e:
            logger.error(f"Error getting available slots for {date_str}: {str(e)}")
            raise

    @staticmethod
    def get_appointments_by_date_range(start_date, end_date):
        """Get appointments within a date range"""
        try:
            return Appointment.query.filter(
                Appointment.date.between(start_date, end_date)
            ).order_by(Appointment.date, Appointment.time).all()
        except Exception as e:
            logger.error(f"Error retrieving appointments in date range: {str(e)}")
            return []

    @staticmethod
    def get_daily_stats():
        """Get appointment statistics for analytics"""
        try:
            today = datetime.now().date()
            month_start = today.replace(day=1)
            
            return {
                'total': Appointment.query.count(),
                'today': Appointment.query.filter_by(date=today).count(),
                'this_month': Appointment.query.filter(
                    Appointment.date >= month_start,
                    Appointment.date <= today
                ).count(),
                'by_service': db.session.query(
                    Appointment.service,
                    func.count(Appointment.id)
                ).group_by(Appointment.service).all()
            }
        except Exception as e:
            logger.error(f"Error getting appointment statistics: {str(e)}")
            return {
                'total': 0,
                'today': 0,
                'this_month': 0,
                'by_service': []
            }
