import streamlit as st
import pandas as pd
import requests
import plotly.express as px
from datetime import datetime, timedelta, timezone


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

def create_bess_schedule(prices_df):
    lowest_prices = prices_df.nsmallest(3, 'NOK_per_kWh')  # Get the 3 lowest prices
    highest_prices = prices_df.nlargest(3, 'NOK_per_kWh')  # Get the 3 highest prices

    prices_df['status'] = 'Idle'

    prices_df.loc[prices_df['datetime'].isin(lowest_prices['datetime']), 'status'] = 'Charge'

    prices_df.loc[prices_df['datetime'].isin(highest_prices['datetime']), 'status'] = 'Discharge'

    return prices_df


def generate_schedule_with_next_day(selected_date):
    selected_day_prices = fetch_day_prices(selected_date)
    next_day_prices = fetch_day_prices(selected_date + timedelta(days=1))

    if selected_day_prices is None or next_day_prices is None:
        return None, None, None, None  # Ensure four return values

    #1st schedule is for 24 hours of the present day
    first_schedule = create_bess_schedule(selected_day_prices.copy())

    #2nd schedule is for from 13:00 hours the present day till the next day midnight
    extended_prices = pd.concat([selected_day_prices[selected_day_prices['hour'] >= 13], next_day_prices])
    extended_schedule = create_bess_schedule(extended_prices.copy())

    return first_schedule, extended_schedule, selected_day_prices, extended_prices


def calculate_cost_savings(first_schedule, extended_schedule, charge_rate, discharge_rate):
    first_schedule_overlap = first_schedule[first_schedule['hour'] >= 13].copy()
    extended_schedule_overlap = extended_schedule[extended_schedule['datetime'].dt.date == first_schedule['datetime'].dt.date.iloc[0]].copy()
    extended_schedule_overlap = extended_schedule_overlap[extended_schedule_overlap['hour'] >= 13]

    first_schedule_overlap = first_schedule_overlap.set_index('datetime')
    extended_schedule_overlap = extended_schedule_overlap.set_index('datetime')

    first_schedule_cost = calculate_schedule_cost(first_schedule_overlap, charge_rate, discharge_rate)
    extended_schedule_cost = calculate_schedule_cost(extended_schedule_overlap, charge_rate, discharge_rate)

    cost_savings = first_schedule_cost - extended_schedule_cost

    return cost_savings


def calculate_schedule_cost(schedule, charge_rate, discharge_rate):
    schedule['cost'] = 0.0
    schedule.loc[schedule['status'] == 'Charge', 'cost'] = - schedule['NOK_per_kWh'] * charge_rate
    schedule.loc[schedule['status'] == 'Discharge', 'cost'] = schedule['NOK_per_kWh'] * discharge_rate

    total_cost = schedule['cost'].sum()
    return total_cost

def main():
    st.title("BESS Schedule Generator and Cost Savings Calculator")
    today = datetime.now(timezone.utc).date()
    selected_date = st.date_input("Please select a date. Today's date is not recommended before 14:00", min_value=datetime(2024, 1, 1).date(), max_value=today)

    charge_rate = st.number_input("Enter Charge Rate (kWh):", min_value=0.1, value=1.0)
    discharge_rate = st.number_input("Enter Discharge Rate (kWh):", min_value=0.1, value=1.0)


    if st.button("Generate Schedule and Calculate Savings"):
        first_schedule, extended_schedule, selected_day_prices, extended_prices = generate_schedule_with_next_day(
            selected_date)

        if selected_day_prices is not None:
            st.write(f"### Spot Prices for {selected_date}")
            fig1 = px.line(selected_day_prices, x='datetime', y='NOK_per_kWh', title=f"Spot Prices for {selected_date}")
            st.plotly_chart(fig1)

        if first_schedule is None or extended_schedule is None:
            st.write("⚠ No spot price data found. Try another date.")
        else:
            st.write(f"### BESS Schedule for {selected_date} (Full Day)")
            st.dataframe(first_schedule)

            st.write(f"### BESS Schedule for {selected_date} (13:00 to 23:59 + Full Next Day)")
            st.dataframe(extended_schedule)

            if extended_prices is not None:
                st.write(f"### Spot Prices from {selected_date} 13:00 to {selected_date + timedelta(days=1)} 24:00")
                fig2 = px.line(extended_prices, x='datetime', y='NOK_per_kWh', title=f"Spot Prices Extended")
                st.plotly_chart(fig2)

            cost_savings = calculate_cost_savings(first_schedule.copy(), extended_schedule.copy(), charge_rate, discharge_rate)
            st.write(f"Cost Savings on {selected_date} during 13:00 to 24:00 with strategic change in schedule : {cost_savings:.2f} NOK")


if __name__ == "__main__":
    main()
