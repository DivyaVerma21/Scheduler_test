import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta, timezone
import logging


def fetch_day_prices(date):
    base_url = "https://www.hvakosterstrommen.no/api/v1/prices"
    formatted_date = date.strftime("%Y/%m-%d")
    url = f"{base_url}/{formatted_date}_NO1.json"

    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        df = pd.DataFrame(data)
        df.rename(columns={'time_start': 'datetime'}, inplace=True)
        df['datetime'] = pd.to_datetime(df['datetime'], utc=True) + timedelta(hours=1)
        df['hour'] = df['datetime'].dt.hour
        return df[['datetime', 'hour', 'NOK_per_kWh']]

    else:
        raise Exception(f"Failed to retrieve data for {date}. Status code: {response.status_code}")



# Function to generate BESS schedule
def create_bess_schedule(prices_df):
    charge_schedule = prices_df[prices_df['NOK_per_kWh'] <= prices_df['NOK_per_kWh'].quantile(0.3)]
    discharge_schedule = prices_df[prices_df['NOK_per_kWh'] >= prices_df['NOK_per_kWh'].quantile(0.7)]
    return charge_schedule, discharge_schedule


def generate_schedule_with_next_day(selected_date):
    selected_day_prices = fetch_day_prices(selected_date)
    next_day_prices = fetch_day_prices(selected_date + timedelta(days=1))

    if selected_day_prices is None or next_day_prices is None:
        return None, None, None, None  # Ensure four return values

    # First schedule: 00:00 - 23:59 on selected day
    charge_schedule, discharge_schedule = create_bess_schedule(selected_day_prices)

    # Second schedule: 13:00 - 23:59 on selected day + 00:00 - 23:59 next day
    extended_prices = pd.concat([selected_day_prices[selected_day_prices['hour'] >= 13], next_day_prices])
    extended_charge_schedule, extended_discharge_schedule = create_bess_schedule(extended_prices)

    return (charge_schedule, discharge_schedule), (
    extended_charge_schedule, extended_discharge_schedule), selected_day_prices, extended_prices


# Streamlit app
def main():
    st.title("BESS Schedule Generator")
    today = datetime.now(timezone.utc).date()
    selected_date = st.date_input("Select a date", min_value=datetime(2024, 1, 1).date(), max_value=today)

    if st.button("Generate Schedule"):
        first_schedule, second_schedule, selected_day_prices, extended_prices = generate_schedule_with_next_day(
            selected_date)

        if selected_day_prices is not None:
            st.write(f"### Spot Prices for {selected_date}")
            fig1 = px.line(selected_day_prices, x='datetime', y='NOK_per_kWh', title=f"Spot Prices for {selected_date}")
            st.plotly_chart(fig1)

        if first_schedule is None or second_schedule is None:
            st.write("⚠ No spot price data found. Try another date.")
        else:
            st.write(f"### BESS Schedule for {selected_date} (Full Day)")
            df_first_schedule = pd.concat([first_schedule[0], first_schedule[1]])
            st.dataframe(df_first_schedule)

            st.write(f"### BESS Schedule for {selected_date} (13:00 to 23:59 + Full Next Day)")
            df_second_schedule = pd.concat([second_schedule[0], second_schedule[1]])
            st.dataframe(df_second_schedule)

            if extended_prices is not None:
                st.write(f"### Spot Prices from {selected_date} 13:00 to {selected_date + timedelta(days=1)} 24:00")
                fig2 = px.line(extended_prices, x='datetime', y='NOK_per_kWh', title=f"Spot Prices Extended")
                st.plotly_chart(fig2)


if __name__ == "__main__":
    main()
