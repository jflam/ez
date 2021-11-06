# Formatting helpers

from rich import print

def format_output_string(text: str, error: bool=False, indent: int=0):
    """Format output string to capitalize first word and colorize based on
    whether it is an error or not"""
    if not text:
        return ''
    first, rest = text.split(' ', 1)
    color = "red" if error else "green"
    spaces = " " * indent
    return f"{spaces}[{color}]{first.upper()}[/{color}] {rest}"

def printf_err(text:str):
    """Print formatted error string"""
    print(format_output_string(f"error: {text}", error=True))

def printf(text:str):
    """Print formatted output string"""
    print(format_output_string(text, error=False))