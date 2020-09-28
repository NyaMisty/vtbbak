import os
from config import load_config
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.json")
load_config(CONFIG_PATH)