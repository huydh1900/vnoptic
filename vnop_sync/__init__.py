import os

from dotenv import load_dotenv

from . import models
from . import wizard
from .hooks import post_init_hook
from . import utils

dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
