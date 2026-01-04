import requests
from core.config import cfg as config

class SPIDER():
    def __init__(self, config_file = "config.yaml"):
        self.ip = config['SPIDER-BOT']['IP_ADDRESS']

    def greet(self):
        if self.ip == None:
            return "Command failed. Retry again."
        else:
            url = f"http://{self.ip}/hello"
            resp = requests.get(url, timeout=10)
            return resp.text
        
    def walk_forward(self, steps: int):
        """Makes the spider bot walk"""
        if self.ip == None:
            return "Command failed. Retry again."
        else:
            url = f"http://{self.ip}/walkForward"
            resp = requests.get(url, timeout=10, params={"steps": steps})
            return resp.text

    def standby(self):
        if self.ip == None:
            return "Command failed. Retry again."
        else:
            url = f"http://{self.ip}/standby"
            resp = requests.get(url, timeout=10)
            return resp.text

    def dance(self, dance_number: int):
        if self.ip == None:
            return "Command failed. Retry again."
        else:
            if dance_number in [1,2,3]:
                url = f"http://{self.ip}/dance{dance_number}"
                resp = requests.get(url, timeout=10)
                return resp.text
            else:
                return f"Invalid dance number. Dance number should be 1,2 or 3."