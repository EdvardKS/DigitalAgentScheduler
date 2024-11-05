import re
from datetime import datetime
from .slots import get_available_slots

def validate_input(field_type, value):
    """Validate user input based on field type"""
    if not value:
        return False
        
    if field_type == 'name':
        return bool(re.match("^[A-Za-zÀ-ÿ\s]{2,100}$", value))
    elif field_type == 'email':
        return bool(re.match(r"[^@]+@[^@]+\.[^@]+", value))
    elif field_type == 'phone':
        # Spanish phone number format (optional +34 prefix)
        return bool(re.match(r"^(?:\+34)?[6789]\d{8}$", value))
    elif field_type == 'service':
        return value.isdigit() and 1 <= int(value) <= 3
    elif field_type == 'date':
        try:
            selected_date = int(value)
            return 1 <= selected_date <= 7
        except ValueError:
            return False
    elif field_type == 'time':
        try:
            slots = get_available_slots()
            if slots and slots[0]['times']:
                return value in slots[0]['times']
        except Exception:
            return False
    return False
