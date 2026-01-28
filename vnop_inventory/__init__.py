# -*- coding: utf-8 -*-
<<<<<<< Updated upstream
=======
from dotenv import load_dotenv
import os

# Load .env file from project root (assuming structure d:/DuAnCaNhan/odoo18/vnoptic/vnop_inventory)
# We go up 3 levels: inventory -> vnoptic -> odoo18 -> .env
env_path = os.path.join(os.path.dirname(__file__), '..', '..', '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

>>>>>>> Stashed changes
# Import folder models để load các class logic
from . import models

# Import folder controllers (nếu sau này cần API hoặc route riêng)
from . import controllers

# Import folder utils (chứa các hàm tiện ích chung)
from . import utils
