'''
Data checks for the tank api project.
'''

def validate_log_data(log_data):
    """
    Validate the log data for required fields and valid values.

    Args:
        log_data (dict): The log data to validate.
    
    Raises:
        ValueError: If any required field is missing or has an invalid value.
    """
    data_fields = {
        'nh3': 'Ammonia',
        'no2': 'Nitrite',
        'no3': 'Nitrate',
        'kh': 'KH',
        'ph': 'pH',
        'temp_f': 'Temperature'
    }
    
    for key, field_name in data_fields.items():
        if log_data.get(key) is None:
            raise ValueError(f"Missing required field: '{field_name}'")
