import json
import logging

logger = logging.getLogger(__name__)

class BookingSession:
    def __init__(self):
        self.state = 'INITIAL'
        self.data = {}
    
    def format_state_data(self):
        """Format state data for internal use"""
        return f"__STATE__{self.state}__DATA__{json.dumps(self.data)}__END__"
    
    @staticmethod
    def extract_state_data(message):
        """Extract state and data from conversation message"""
        if not message or '__STATE__' not in message:
            return None, None
        try:
            state = message.split('__STATE__')[1].split('__DATA__')[0]
            data_str = message.split('__DATA__')[1].split('__END__')[0]
            return state, json.loads(data_str)
        except Exception as e:
            logger.error(f"Error extracting state data: {str(e)}")
            return None, None
