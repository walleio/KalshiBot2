import torch
from nn import KalshiCNN
import json
import os
import datetime
import time
from dotenv import load_dotenv
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import requests

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.exceptions import InvalidSignature

class Client:
    def __init__(self):
        load_dotenv()
        self.KEYID = os.getenv('PROD_KEYID')
        self.KEYFILE = os.getenv('PROD_KEYFILE')


    @staticmethod
    def _load_private_key_from_file(file_path):
        with open(file_path, "rb") as key_file:
            private_key = serialization.load_pem_private_key(
                key_file.read(),
                password=None,  # or provide a password if your key is encrypted
                backend=default_backend()
            )
        return private_key

    @staticmethod
    def sign_pss_text(private_key: rsa.RSAPrivateKey, text: str) -> str:
        # Before signing, we need to hash our message.
        # The hash is what we actually sign.
        # Convert the text to bytes
        message = text.encode('utf-8')
        try:
            signature = private_key.sign(
                message,
                padding.PSS(
                    mgf=padding.MGF1(hashes.SHA256()),
                    salt_length=padding.PSS.DIGEST_LENGTH
                ),
                hashes.SHA256()
            )
            return base64.b64encode(signature).decode('utf-8')
        except InvalidSignature as e:
            raise ValueError("RSA sign PSS failed") from e

        return signature

    def generate_signature(self, path):
        method = 'POST'
        current_time = datetime.datetime.now()
        timestamp = current_time.timestamp()
        current_time_milliseconds = int(timestamp * 1000)
        timestamp_str = str(current_time_milliseconds)
        private_key = self._load_private_key_from_file(self.KEYFILE)

        msg_string = timestamp_str + method + path
        sig = self.sign_pss_text(private_key, msg_string)
        return sig, timestamp_str

'''
inference_model = KalshiCNN(118)
#inference_model.load_state_dict(torch.load("model.pth", map_location=device))
inference_model.eval()  

url = "https://api.elections.kalshi.com/trade-api/v2/events"

# dates formatted like yyMONTHdd
weather = ['KXHIGHCHI-25APR21', 'KXHIGHDEN-25APR21', 'KXHIGHNY-25APR21', 'KXHIGHLAX-25APR21', 'KXHIGHLAX-25APR21', 'KXHIGHAUS-25APR21', 'KXHIGHPHIL-25APR21']

events = []

for event_ticker in weather:
    final_url = url + f'/{event_ticker}?with_nested_markets=true'

    headers = {"accept": "application/json"}

    response = requests.get(final_url, headers=headers)

    events.append(json.loads(response.text))

candlesticks = {}
candlesticks[event_ticker] = {}
for event in events:
    for market in event['event']['markets']:
        ticker = market['ticker']
        series_ticker = event['event']['series_ticker']

        url = f'https://api.elections.kalshi.com/trade-api/v2/series/{series_ticker}/markets/{ticker}/candlesticks'

        start_ts = int(time.time()) - 3600
        end_ts = int(time.time())
        
        # get data every 1 minute
        period_interval = 1

        # get data from the start_ts to the start_ts + 60 minutes
        url = url + f'?start_ts={start_ts}&end_ts={start_ts + 60 * 60}&period_interval={period_interval}'

        headers = {"accept": "application/json"}

        response = requests.get(url, headers=headers)

        try:
            candlesticks[event_ticker][ticker] = response.json()['candlesticks'][:100] if len(response.json()['candlesticks']) > 100 else response.json()['candlesticks']
        except:
            print(response.text)

print(len(candlesticks))
'''
#with torch.no_grad():
    #single_pred = inference_model(x).item()   

client = Client()

ticker = 'KXHIGHPHIL-25APR21-T70'
url = "https://api.elections.kalshi.com"

# url_sell = url + "?action=sell&count=1&side=yes&ticker={ticker}&type=market"

sig, timestamp_str = client.generate_signature(url)

body = {
    "action": "buy",
    "count" : 1,
    "side"  : "yes",
    "ticker": ticker,
    "type"  : "market"
}

headers = {
    "accept": "application/json",
    "content-type": "application/json",
    'KALSHI-ACCESS-KEY': client.KEYID,
    'KALSHI-ACCESS-SIGNATURE': sig,
    'KALSHI-ACCESS-TIMESTAMP': timestamp_str
}

response_buy = requests.post(url, headers=headers, json=body)
# response_sell = requests.get(url_sell, headers=headers)

print(response_buy.text)
# print(response_sell.text)