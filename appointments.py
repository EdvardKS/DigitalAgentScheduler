from datetime import datetime, time, timedelta
from models import db, Appointment
from email_utils import send_appointment_confirmation, schedule_reminder_email
import re
from typing import Dict, Optional, Tuple
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AppointmentManager:
    # Constants for validation
    MIN_NAME_LENGTH = 2
    MAX_NAME_LENGTH = 100
    VALID_SERVICES = ["AI Development", "AI Consulting", "Web Development"]
    BUSINESS_HOURS = {
        "start": time(10, 30),  # 10:30 AM
        "end": time(14, 0)      # 2:00 PM
    }
    
    @staticmethod
    def validate_email(email: str) -> Tuple[bool, str]:
        """Validate email format"""
        email_pattern = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')
        if not email_pattern.match(email):
            return False, "Invalid email format"
        return True, ""

    @staticmethod
    def validate_name(name: str) -> Tuple[bool, str]:
        """Validate name length and format"""
        if len(name) < AppointmentManager.MIN_NAME_LENGTH:
            return False, f"Name must be at least {AppointmentManager.MIN_NAME_LENGTH} characters"
        if len(name) > AppointmentManager.MAX_NAME_LENGTH:
            return False, f"Name must not exceed {AppointmentManager.MAX_NAME_LENGTH} characters"
        if not name.replace(" ", "").isalpha():
            return False, "Name should only contain letters"
        return True, ""

    @staticmethod
    def validate_service(service: str) -> Tuple[bool, str]:
        """Validate if service is available"""
        if service not in AppointmentManager.VALID_SERVICES:
            return False, "Invalid service selected"
        return True, ""

    @staticmethod
    def validate_date(date_str: str) -> Tuple[bool, str]:
        """Validate appointment date"""
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            today = datetime.now().date()
            
            # Check if date is in the future
            if date < today:
                return False, "Cannot book appointments in the past"
            
            # Check if date is within 30 days
            if date > today + timedelta(days=30):
                return False, "Cannot book appointments more than 30 days in advance"
            
            # Check if it's a weekday
            if date.weekday() >= 5:
                return False, "Appointments are only available on weekdays"
            
            return True, ""
        except ValueError:
            return False, "Invalid date format"

    @staticmethod
    def validate_time(time_str: str) -> Tuple[bool, str]:
        """Validate appointment time"""
        try:
            appointment_time = datetime.strptime(time_str, "%H:%M").time()
            
            # Check if time is within business hours
            if (appointment_time < AppointmentManager.BUSINESS_HOURS["start"] or 
                appointment_time > AppointmentManager.BUSINESS_HOURS["end"]):
                return False, "Appointments are only available between 10:30 AM and 2:00 PM"
            
            # Check if time is at 30-minute intervals
            if appointment_time.minute not in [0, 30]:
                return False, "Appointments must be scheduled at 30-minute intervals"
            
            return True, ""
        except ValueError:
            return False, "Invalid time format"

    @staticmethod
    def check_availability(date: str, time: str) -> Tuple[bool, str]:
        """Check if the time slot is available"""
        try:
            existing_appointment = Appointment.query.filter_by(
                date=datetime.strptime(date, "%Y-%m-%d").date(),
                time=time
            ).first()
            
            if existing_appointment:
                return False, "This time slot is already booked"
            return True, ""
        except Exception as e:
            logger.error(f"Error checking availability: {str(e)}")
            return False, "Error checking appointment availability"

    @classmethod
    def create_appointment(cls, appointment_data: Dict) -> Tuple[bool, str, Optional[Appointment]]:
        """Create a new appointment with validation"""
        try:
            # Validate all fields
            validations = [
                cls.validate_name(appointment_data.get('name', '')),
                cls.validate_email(appointment_data.get('email', '')),
                cls.validate_service(appointment_data.get('service', '')),
                cls.validate_date(appointment_data.get('date', '')),
                cls.validate_time(appointment_data.get('time', ''))
            ]

            # Check if any validation failed
            for is_valid, message in validations:
                if not is_valid:
                    return False, message, None

            # Check availability
            is_available, availability_message = cls.check_availability(
                appointment_data['date'],
                appointment_data['time']
            )
            if not is_available:
                return False, availability_message, None

            # Create appointment
            appointment = Appointment(
                name=appointment_data['name'],
                email=appointment_data['email'],
                service=appointment_data['service'],
                date=datetime.strptime(appointment_data['date'], "%Y-%m-%d").date(),
                time=appointment_data['time']
            )

            # Save to database
            try:
                db.session.add(appointment)
                db.session.commit()
                
                # Send confirmation email and schedule reminder
                send_appointment_confirmation(appointment)
                schedule_reminder_email(appointment)
                
                return True, "Appointment created successfully", appointment
            except Exception as e:
                db.session.rollback()
                logger.error(f"Database error: {str(e)}")
                return False, "Error creating appointment", None

        except Exception as e:
            logger.error(f"Error in create_appointment: {str(e)}")
            return False, "Internal server error", None

    @staticmethod
    def cancel_appointment(appointment_id: int) -> Tuple[bool, str]:
        """Cancel an existing appointment"""
        try:
            appointment = Appointment.query.get(appointment_id)
            if not appointment:
                return False, "Appointment not found"

            if appointment.date < datetime.now().date():
                return False, "Cannot cancel past appointments"

            db.session.delete(appointment)
            db.session.commit()
            return True, "Appointment cancelled successfully"
        except Exception as e:
            db.session.rollback()
            logger.error(f"Error cancelling appointment: {str(e)}")
            return False, "Error cancelling appointment"

    @staticmethod
    def get_available_slots(date_str: str) -> list:
        """Get available time slots for a given date"""
        try:
            date = datetime.strptime(date_str, "%Y-%m-%d").date()
            
            # If weekend or past date, return empty list
            if date < datetime.now().date() or date.weekday() >= 5:
                return []

            # Generate all possible slots
            slots = []
            current_time = AppointmentManager.BUSINESS_HOURS["start"]
            end_time = AppointmentManager.BUSINESS_HOURS["end"]

            while current_time <= end_time:
                time_str = current_time.strftime("%H:%M")
                
                # Check if slot is already booked
                existing_appointment = Appointment.query.filter_by(
                    date=date,
                    time=time_str
                ).first()
                
                if not existing_appointment:
                    slots.append(time_str)
                
                # Move to next 30-minute slot
                if current_time.minute == 30:
                    current_time = time(current_time.hour + 1, 0)
                else:
                    current_time = time(current_time.hour, 30)

            return slots
        except Exception as e:
            logger.error(f"Error getting available slots: {str(e)}")
            return []
