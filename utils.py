from constants import BASE_URL

def build_url(query_template: str, symbol: str, apikey: str) -> str:
    """Build the full URL for the API request.
    Args:
        query_template (str): The query template with placeholders.
        symbol (str): The stock symbol.
        apikey (str): The API key.
    Returns:
        str: The complete URL for the API request.
    Raises:
        ExceptionType: Description of the exception raised.
    """
    return BASE_URL + query_template.format(symbol=symbol, apikey=apikey)