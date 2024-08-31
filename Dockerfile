
FROM python:3.10-slim

WORKDIR /usr/vihariApi/

COPY ./ /usr/vihariApi/

RUN pip install -r requirements.txt 

RUN pip install gunicorn

CMD ["python", "app.py"]
