import requests
import json
from requests.adapters import HTTPAdapter
from datetime import datetime, timezone
import pandas as pd
from urllib3.util.retry import Retry

# this code is not critical to understand; it just increases API call reliability and efficiency
retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)

# instantiate the requests session
session = requests.Session()
session.headers.update({"accept": "application/json"})
session.mount("https://", adapter)

# get the data for training the model
def get_events():
    url = "https://api.elections.kalshi.com/trade-api/v2/events"

    # these are the events that will be used to train the model
    # dates formatted like yyMONTHdd
    weather = ['KXHIGHCHI-', 'KXHIGHDEN-', 'KXHIGHNY-', 'KXHIGHLAX-', 'KXHIGHAUS-', 'KXHIGHPHIL-']

    # these dates combined with the values in the previous list give the names of markets that can be traded
    march_dates = [f'25MAR{str(day).zfill(2)}' for day in range(1, 32)]
    april_dates = [f'25APR{str(day).zfill(2)}' for day in range(1, 30)]
    may_dates = [f'25MAY{str(day).zfill(2)}' for day in range(1, 23)]
    all_dates = march_dates + april_dates + may_dates
    
    # create all combinations of weather stations and dates
    weather_with_date = [w + date for w in weather for date in all_dates]

    events = []

    # this just gets the events for the markets that can be traded
    for event_ticker in weather_with_date:
        final_url = url + f'/{event_ticker}?with_nested_markets=true'

        headers = {"accept": "application/json"}

        response = session.get(final_url, headers=headers)

        events.append(json.loads(response.text))

    return events

def get_candlesticks(events):
    # series > event > market: each event has multiple markets; each event lasts a day but is contained within a series (more info in the decider.py file)

    # candlesticks contain historial pricing data for each market
    candlesticks = []

    for event in events:
        for market in event['event']['markets']:
            ticker = market['ticker']
            series_ticker = event['event']['series_ticker']

            url = f'https://api.elections.kalshi.com/trade-api/v2/series/{series_ticker}/markets/{ticker}/candlesticks'

            start_ts = market['open_time']
            end_ts = market['close_time']

            # some times have microseconds; get rid of the microseconds
            if '.' in start_ts:
                start_ts = start_ts.split('.')[0] + 'Z'
            if '.' in end_ts:
                end_ts = end_ts.split('.')[0] + 'Z'

            # convert the start and end times to timestamps (the format given by the api is not appropriate for api calls - yes, this is odd)
            start_ts = int(datetime.strptime(start_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
            end_ts = int(datetime.strptime(end_ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp())
            
            # get data every 1 minute
            period_interval = 1
            while start_ts < end_ts:
                # get data from the start_ts to the start_ts + 100 minutes
                full_url = url + f'?start_ts={start_ts}&end_ts={start_ts+60*100}&period_interval={period_interval}'

                headers = {"accept": "application/json"}

                response = session.get(full_url, headers=headers)
                try:
                    # get just the last 100 candlesticks (might be redundant step considering the above api call)
                    candlesticks.append(response.json()['candlesticks'][:100] if len(response.json()['candlesticks']) > 100 else response.json()['candlesticks'])
                except:
                    print(response.text)

                # increment the start_ts by 100 minutes and get the next 100 candlesticks
                start_ts += 60 * 100

        # if the number of candlesticks is greater than 1000000, break
        # this is arbitrary; if you want more data, increase the number (and vice versa)
        if len(candlesticks) > 1000000:
            break

    return candlesticks

# get the candlesticks
candlesticks = get_candlesticks(get_events())

# create the data and labels for training the model
data = []
labels = []
for candlestick_group in candlesticks:
    # every 60th candlestick is the label
    [(data.append(candlestick_group[:i]), labels.append(candlestick)) for i, candlestick in enumerate(candlestick_group) if i % 59 == 0 and i != 0]

# save the data and labels
pd.DataFrame({'dict': data}).to_csv('data.csv', index=False)
pd.DataFrame({'dict': labels}).to_csv('labels.csv', index=False)

