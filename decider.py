import requests
import json
import time
from nn import KalshiCNN
import ast
import torch 
from client import Client
import copy
import math

url = "https://api.elections.kalshi.com/trade-api/v2/events"
# the days for which you would like to trade
weather = ['KXHIGHCHI-25MAY28', 'KXHIGHDEN-25MAY28', 'KXHIGHNY-25MAY28', 'KXHIGHLAX-25MAY28', 'KXHIGHLAX-25MAY28', 'KXHIGHAUS-25MAY28', 'KXHIGHPHIL-25MAY28']

# this, with the next for loop, will get the markets for the events you want to trade
# definitionally, the markets are the yes/no bets for the event (e.g., an event is the weather in Chicago on May 28, 2025 and 
# a particular market is 'will the high temperature be between 60 and 61 degrees?')
events = []

for event_ticker in weather:
    final_url = url + f'/{event_ticker}?with_nested_markets=true'

    headers = {"accept": "application/json"}

    response = requests.get(final_url, headers=headers)

    events.append(json.loads(response.text))

# get the candlesticks (essentially volatility data) for the markets you want to trade
def get_candlesticks(events):
    candlesticks = {}
    for event in events:
        for market in event['event']['markets']:
            # if there is no volume, the market is stagnant and shouldn't be traded
            if market['volume'] == 0:
                continue

            # markets have their own tickers, distinct from the event ticker
            ticker = market['ticker']

            # this should be almost disregarded and is only necessary for the api call
            # however, the series ticker is a broader category of the event ticker
            # e.g., a series ticker might denote all weather events for Chicago, whereas an event
            # ticker is only one day
            series_ticker = event['event']['series_ticker']

            url = f'https://api.elections.kalshi.com/trade-api/v2/series/{series_ticker}/markets/{ticker}/candlesticks'

            # get the candlestick data for the previous 4 hours
            start_ts = int(time.time()) - (14400 * 2)
            end_ts = int(time.time())
            
            # get data every 1 minute
            period_interval = 1

            url = url + f'?start_ts={start_ts}&end_ts={end_ts}&period_interval={period_interval}'

            headers = {"accept": "application/json"}
            response = requests.get(url, headers=headers)

            try:
                # only trade on the last hour of data (i.e., the last 59 candlesticks)
                candlesticks[ticker] = response.json()['candlesticks'][-59:] if len(response.json()['candlesticks']) > 59 else response.json()['candlesticks']
            except:
                pass

    return candlesticks

# parse the candlestick data into a list of floats
def parse_dict(s):
    out = []
    for d in s:
        out.extend([d['yes_bid']['open'], d['volume']])
    return out

# load the model
inference_model = torch.load("model.pth")
inference_model.eval()

# initialize the client (used for api calls)
client = Client()

# make the input for the model the proper shape
def get_item(dicts):
    if len(dicts) == 0:
        return None 
    numeric = parse_dict(dicts)
    pad_needed = (59 * 2 - len(numeric))
    numeric.extend([0.0]*pad_needed)
    x = torch.tensor(numeric, dtype=torch.float32).view(1, 2, 59)

    return x

# a couple of safeguards to avoid buying in dangerous edge cases
def verify_buyability(ticker):
    url_orderbook = f'https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}/orderbook'
    url_market = f'https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}'
    headers = {"accept": "application/json"}

    # get the orderbook data (data regarding the demand for a bid)
    response_orderbook = requests.get(url_orderbook, headers=headers)
    orderbook = response_orderbook.json()

    # get the market data (data regarding the last price (sell offer))
    response_market = requests.get(url_market, headers=headers)
    market = response_market.json()
    yes_ask = market['market']['last_price']

    # get the last actual bid
    yes_offer = orderbook['orderbook']['yes']

    # if there are no offers, don't buy because it may be 
    # impossible to sell later on
    # for example, if the bot wants to buy a 1 cent conract, predicting it will go up 2 cents,
    # it will never be able to sell, leading to a loss
    if yes_offer == [] or yes_offer == None:
        return False, None
    
    # if the last ask is less than the last bid + 2 cents, buy
    if yes_ask < yes_offer[-1][0] + 2:
        return True, yes_ask
    else:
        return False, None
    
# a couple of safeguards to sell when a position is suffering
def verify_sellability(ticker, original_price):
    url_orderbook = f'https://api.elections.kalshi.com/trade-api/v2/markets/{ticker}/orderbook'
    headers = {"accept": "application/json"}

    # get the orderbook data (data regarding the demand for a bid)
    response_orderbook = requests.get(url_orderbook, headers=headers)
    orderbook = response_orderbook.json()
    
    # get the last actual bid
    yes_offer = orderbook['orderbook']['yes']

    if yes_offer == [] or yes_offer == None:
        return False, None

    # if the price at the time you purchased the position is less than the last bid, sell
    if original_price < yes_offer[-1][0]:
        return True, yes_offer[-1][0]
    else:
        return False, None

def buy_holdings(candlesticks, holdings):
    for key, value in candlesticks.items():
        # get the properly formmated input for the model
        data = get_item(value)
        if data is not None:
            with torch.no_grad():
                # have the model evaluate the input
                model_output = inference_model(data)
            
            # if the last bid is less than the model's prediction, buy
            if value[-1]['yes_bid']['open'] < model_output.item():
                # verify buyability first, using logic from verify_buyability
                buyable, yes_ask = verify_buyability(key)
                if buyable:
                    # make the api call to buy
                    result = client.make_request(key, 'buy', yes_ask, count=1)
                    # print the result of the api call
                    print(f'{key} bought, status: {result[0]}')

def sell_holdings(holdings, candlesticks, currently_selling):
    keys_to_delete = []
    for key, value in currently_selling.items():
        if time.time() - value > 180:
            keys_to_delete.append(key)
    
    for key in keys_to_delete:
        del(currently_selling[key])

    for key, value in candlesticks.items():
        data = get_item(value)
        if data is not None:
            with torch.no_grad():
                # have the model evaluate the input, to get a prediction for whether or not the price will go down
                model_output = inference_model(data)
            # if you currently own the position and its last bid is greater than the model's prediction, sell
            if key in holdings and value[-1]['yes_bid']['open'] > model_output.item():

                # verify sellability first, using logic from verify_sellability
                sellable, yes_offer = verify_sellability(key, holdings[key]['price'])

                # if the position is not already being sold and the position is sellable, sell
                # there is a 3 minute cooldown between limit order sells
                already_selling = True if key in currently_selling and time.time() - currently_selling[key] < 180 else False

                # if the position is sellable and not already being sold, sell  
                if sellable and not already_selling:
                    # make the api call to sell
                    result = client.make_request(key, 'sell', yes_offer, count=holdings[key]['posn']) 
                    # print the result of the api call
                    print(f'{key} sold, status: {result[0]}')
                    # delete the position from the holdings
                    del(holdings[key])
                    # add the position to the list of positions being sold
                    currently_selling[key] = time.time()
    
    return currently_selling

    # if the position has lost more than 5 cents, sell
    holdings_copy = copy.deepcopy(holdings)
    for key, value in holdings.items():
        # if the position has lost more than 5 cents, sell
        if value['price'] - value['value'] > 5:
            # make the api call to sell
            result = client.make_request(key, 'sell', math.floor(value['price']), count=holdings[key]['posn']) 
            # print the result of the api call
            print(f'{key} sold, status: {result[0]}')
            # delete the position from the holdings
            del(holdings_copy[key])
            # add the position to the list of positions being sold
            currently_selling.append({key: time.time()})

    holdings = holdings_copy
    return currently_selling

# testing variable to control whether or not the bot can buy
can_buy = True

currently_selling = {}
while True:
    print(currently_selling)
    holdings = client.get_positions()
    candlesticks = get_candlesticks(events)
    if can_buy:
        buy_holdings(candlesticks, holdings)
        holdings = client.get_positions()
    time.sleep(60)
    currently_selling = sell_holdings(holdings, candlesticks, currently_selling)