FROM python:3.12-slim

WORKDIR /app

COPY . /app
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY main.py /app/main.py
COPY db.py /app/db.py
COPY models.py /app/models.py
COPY templates /app/templates

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
