FROM python:3.8.4-slim

RUN mkdir /github_bot
WORKDIR /github_bot
COPY . /github_bot/
RUN pip install -r requirements.txt
ENTRYPOINT ["python", "bot.py"]
