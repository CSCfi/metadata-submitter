"""
Extracts setting different configurations like environmental variables to
separe file
"""
from dotenv import load_dotenv, find_dotenv


def init_loadenv():
    """ Load environment variables with python-dotenv """
    load_dotenv(find_dotenv())
