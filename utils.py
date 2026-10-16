'''Utility functions for the TankPi application.'''

def calculate_toxic_ammonia(data_dict):
    """
    Calculate the toxic ammonia (NH3) concentration based on the provided parameters.

    Parameters:
        data_dict: list[dict[str, float]]
            A list of dictionaries, each containing the following keys:
            - 'temp_f': Temperature in Fahrenheit (float)
            - 'ph': pH level (float)
            - 'nh3': Ammonia concentration in ppm (float)
    Returns:
        float: The calculated toxic ammonia concentration in ppm.
    """
    toxic_ammonia_over_time = []
    for row in data_dict:
        # Convert temperature from Fahrenheit to Celsius
        temp_k = (row['Temperature'] - 32) * (5.0 / 9.0) + 273.15

        # Calculate the fraction of NH3 based on pH and temperature
        fraction_nh3 = 1 / (1 + 10 ** (9.25 - row['pH']) * (1 + 0.033 * temp_k))

        # Calculate toxic ammonia concentration
        toxic_ammonia = row['Ammonia'] * fraction_nh3
        toxic_ammonia_over_time.append(toxic_ammonia)

    return toxic_ammonia_over_time