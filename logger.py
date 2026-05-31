import datetime

def log(message):
    with open("logs.txt", "a") as f:
        time = datetime.datetime.now()
        f.write(f"{time} - {message}\n")