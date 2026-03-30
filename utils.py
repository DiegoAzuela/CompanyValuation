# utils.py
from constants import BASE_URL

def read_api_key(path: str) -> str:
    """Reads the API key from a file.
    
    Args:
        path (str): Path to the file containing the API key.
    
    Returns:
        str: The API key.
    """
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        raise Exception(f"API key file not found: {path}")
    except Exception as e:
        raise Exception(f"Error reading API key: {e}")


def build_url(query_template: str, symbol: str, apikey: str) -> str:
    """Build the full URL for the API request.
    
    Args:
        query_template (str): The query template with placeholders.
        symbol (str): The stock symbol.
        apikey (str): The API key.
    
    Returns:
        str: The complete URL for the API request.
    """
    return BASE_URL + query_template.format(symbol=symbol, apikey=apikey)
