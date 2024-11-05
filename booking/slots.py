from datetime import datetime, timedelta
import logging
from models import db, Appointment
from sqlalchemy.exc import SQLAlchemyError, OperationalError
from contextlib import contextmanager
import time

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
RETRY_DELAY = 1  # seconds

@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = db.session
    try:
        yield session
        session.commit()
    except Exception as e:
        session.rollback()
        raise
    finally:
        session.close()

def get_available_slots():
    """Get available appointment slots with improved error handling and session management"""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            slots = []
            current_date = datetime.now()
            
            with session_scope() as session:
                # Get next 7 available weekdays
                for i in range(14):  # Look ahead 14 days to find 7 available slots
                    check_date = current_date + timedelta(days=i)
                    if check_date.weekday() < 5:  # Monday = 0, Friday = 4
                        # Use the session from context manager
                        booked_times = set(
                            apt.time for apt in session.query(Appointment).filter_by(
                                date=check_date.date()
                            ).all()
                        )
                        
                        # Available time slots
                        available_times = []
                        start_time = datetime.strptime("10:30", "%H:%M")
                        end_time = datetime.strptime("14:00", "%H:%M")
                        current_time = start_time
                        
                        while current_time <= end_time:
                            time_str = current_time.strftime("%H:%M")
                            if time_str not in booked_times:
                                available_times.append(time_str)
                            current_time += timedelta(minutes=30)
                        
                        if available_times:
                            slots.append({
                                'date': check_date.strftime("%Y-%m-%d"),
                                'formatted_date': check_date.strftime('%-d de %B de %Y').lower(),
                                'times': available_times
                            })
                        
                        if len(slots) >= 7:
                            break
            
            return slots
            
        except OperationalError as e:
            retries += 1
            logger.error(f"Database connection error (attempt {retries}/{MAX_RETRIES}): {str(e)}")
            if retries < MAX_RETRIES:
                time.sleep(RETRY_DELAY * (2 ** retries))
            else:
                logger.error("Maximum retries reached for database connection")
                raise
        except SQLAlchemyError as e:
            logger.error(f"Database query error: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in get_available_slots: {str(e)}")
            raise
