import os
import sys
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta
from requests.auth import HTTPBasicAuth

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# API Credentials & URLs (Replace these with actual values or use environment variables)
SITE_ID = "b36a1513-381c-434a-ae9b-08ea05464ddc"
API_URL = f"https://ems.greenerway.services/api/v1/sites/b36a1513-381c-434a-ae9b-08ea05464ddc/measurements/realtime"
API_USERNAME = "batteri"
API_PASSWORD = "batteri"
BATTERY_CAPACITY = 5.6  # Example capacity in kWh
SCHEDULE_URL = f"https://ems.greenerway.services/api/v1/sites/b36a1513-381c-434a-ae9b-08ea05464ddc/schedule"
SPOT_PRICE_API_BASE = "https://www.hvakosterstrommen.no/api/v1/prices"


def fetch_battery_soc_and_site_load():

    try:
        response = requests.get(API_URL, auth=HTTPBasicAuth(API_USERNAME, API_PASSWORD))
        response.raise_for_status()
        data = response.json()
        battery_soc = data.get('batterySoc')
        site_load = data.get('siteLoad')
        return battery_soc, site_load
    except requests.RequestException as e:
        logging.error(f"Failed to fetch SoC and site load: {e}")
        return None, None


def fetch_day_prices(date):

    formatted_date = date.strftime("%Y/%m-%d")
    url = f"{SPOT_PRICE_API_BASE}/{formatted_date}_NO1.json"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        df = pd.DataFrame(data)
        df.rename(columns={'time_start': 'datetime'}, inplace=True)
        df['datetime'] = pd.to_datetime(df['datetime'], utc=True) + timedelta(hours=1)
        df['hour'] = df['datetime'].dt.hour
        return df[['datetime', 'hour', 'NOK_per_kWh']]
    except requests.RequestException as e:
        logging.error(f"Failed to retrieve prices for {date}: {e}")
        return None


def create_bess_schedule():
    now = datetime.utcnow()
    today = now.date()
    tomorrow = today + timedelta(days=1)

    # Fetch today's prices first
    price_df = fetch_day_prices(today)
    if now.hour >= 13:
        next_day_prices = fetch_day_prices(tomorrow)
        if next_day_prices is not None:
            price_df = pd.concat([price_df, next_day_prices])

    if price_df is None or price_df.empty:
        logging.warning("No spot price data available. Cannot generate schedule.")
        return

    # Select the three lowest-priced hours for charging
    lowest_prices = price_df.nsmallest(3, 'NOK_per_kWh')
    charge_schedule = [
        {"datetime": row['datetime'].strftime("%Y-%m-%d %H:%M"), "action": "charge"}
        for _, row in lowest_prices.iterrows()
    ]

    # Select the three highest-priced hours for discharging
    highest_prices = price_df.nlargest(3, 'NOK_per_kWh')
    discharge_schedule = [
        {"datetime": row['datetime'].strftime("%Y-%m-%d %H:%M"), "action": "discharge"}
        for _, row in highest_prices.iterrows()
    ]

    # Combine both schedules
    schedule = charge_schedule + discharge_schedule

    logging.info("Generated BESS Charge schedule:")
    for entry in charge_schedule:
        logging.info(f"Charge at {entry['datetime']}")

    logging.info("Generated BESS Discharge schedule:")
    for entry in discharge_schedule:
        logging.info(f"Discharge at {entry['datetime']}")


if __name__ == "__main__":
    battery_soc, site_load = fetch_battery_soc_and_site_load()
    if battery_soc is not None:
        logging.info(f"Current Battery SoC: {battery_soc}%")
    if site_load is not None:
        logging.info(f"Current Site Load: {site_load} kW")
    create_bess_schedule()