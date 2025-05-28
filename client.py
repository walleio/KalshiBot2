import time, os, json, base64, requests
from dotenv import load_dotenv
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
import random

# code for making api calls - a lot of this comes from the Kalshi API documentation
# I will comment and explain the code that is critical to understanding the bot
class Client:
    def __init__(self):
        load_dotenv()
        # set your environment variables (more information can be found online and on the Kalshi website)
        self.KEY_ID = os.getenv("PROD_KEYID")
        self.KEY_FILE = os.getenv("PROD_KEYFILE")

    def load_key(self, path) -> rsa.RSAPrivateKey:
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), None)

    def sign(self, privkey, msg: str) -> str:
        sig = privkey.sign(
            msg.encode(),
            padding.PSS(mgf=padding.MGF1(hashes.SHA256()),
                        salt_length=padding.PSS.DIGEST_LENGTH),
            hashes.SHA256(),
        )
        return base64.b64encode(sig).decode()

    # make the api call to buy or sell
    def make_request(self, ticker, action, yes_price, count=1):
        priv = self.load_key(self.KEY_FILE)

        method = "POST"
        path   = "/trade-api/v2/portfolio/orders"

        # get the current timestamp (getting rid of milliseconds)
        ts     = str(int(time.time()*1000))
        msg    = ts + method + path

        headers = {
            "KALSHI-ACCESS-KEY":       self.KEY_ID,
            "KALSHI-ACCESS-SIGNATURE": self.sign(priv, msg),
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type":            "application/json",
            "accept":                  "application/json"
        }

        # generate a random id for the order, a new id needs to be used for each order, so if an order
        # is placed at the same second as another order, the random number will ensure that the ids are different
        id = str(int(time.time())) + str(random.randint(1, 1000))

        # place a limit order buy at the price of the last bid (hoping there is an offer at that price), expires in 3 minutes
        if action == 'buy':
            body = {
                "action": action,
                "count" : count,
                "side"  : "yes",
                "ticker": ticker,
                "type"  : "limit",
                "yes_price": yes_price,
                "client_order_id": id,
                "expiration_ts": int(time.time()) + 180
            }

        # place a limit order sell at the last bid for the contract, expires in 3 minutes
        elif action == 'sell':
            body = {
                "action": action,
                "count" : count,
                "side"  : "yes",
                "ticker": ticker,
                "type"  : "limit",
                "yes_price": int(yes_price),
                "client_order_id": id,
                "expiration_ts": int(time.time()) + 180
            }

        # make the api call
        r = requests.post("https://api.elections.kalshi.com" + path, headers=headers, json=body)

        return r.status_code, r.text
    
    # get the positions you currently own
    def get_positions(self):
        method = "GET"
        path   = "/trade-api/v2/portfolio/positions"
        ts     = str(int(time.time()*1000))
        msg    = ts + method + path

        priv = self.load_key(self.KEY_FILE)
        headers = {
            "KALSHI-ACCESS-KEY":       self.KEY_ID,
            "KALSHI-ACCESS-SIGNATURE": self.sign(priv, msg),
            "KALSHI-ACCESS-TIMESTAMP": ts,
            "Content-Type":            "application/json",
            "accept":                  "application/json"
        }

        positions = requests.get('https://api.elections.kalshi.com/trade-api/v2/portfolio/positions', headers = headers)

        # format the positions so that they hold the ticker, how much was paid per contract, and the current value of the position
        holdings = {
            mp["ticker"]: {"posn": mp["position"], "price": int(mp['market_exposure'] / mp['position']), "value": requests.get(f'https://api.elections.kalshi.com/trade-api/v2/markets/{mp["ticker"]}').json()['market']['yes_bid']}
            for mp in positions.json()['market_positions']
            if mp["position"] != 0
        }
        return holdings