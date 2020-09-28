import os
import json

CONFIG = {
    "cookie": "",
    "prefer_cdn": 'upos-sz-mirrorkodo.bilivideo.com',
    "workdir": '/mnt/nfs',
    "redis": "redis://172.23.115.120",
    "amqp": 'pyamqp://guest:guest@172.23.115.120:5672'
}
def load_config():
    path = os.path.join(os.path.dirname(__file__), "config.json")
    try:
        with open(path, 'r') as f:
            CONFIG.update(json.load(f))
    except Exception as e:
        print("Failed to parse the config!")

load_config()