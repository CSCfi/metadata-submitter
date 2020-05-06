"""
Extracts setting different configurations like environmental variables to
separe file
"""

from dotenv import find_dotenv, load_dotenv


def init_loadenv():
    """ Load environment variables with python-dotenv """
    load_dotenv(find_dotenv())
