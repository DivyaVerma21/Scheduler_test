FROM python:3.10

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir requirements.txt

COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "bess_schedule.py", "--server.port=8501", "--server.address=0.0.0.0"]