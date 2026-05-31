from pathlib import Path
from datetime import datetime
import uuid
import time
import os

BASE_DIR = Path("data")

def get_input_path(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    folder = BASE_DIR / "inputs" / today / f"user_{user_id}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"{uuid.uuid4()}.csv"


def get_output_path(user_id):
    today = datetime.now().strftime("%Y-%m-%d")
    folder = BASE_DIR / "outputs" / today / f"user_{user_id}"
    folder.mkdir(parents=True, exist_ok=True)
    return folder / f"result_{uuid.uuid4()}.csv"

def cleanup_old_files(folder="data", days=3):
    now = time.time()
    cutoff = now - (days * 86400)

    for root, dirs, files in os.walk(folder):
        for file in files:
            path = os.path.join(root, file)
            if os.path.getmtime(path) < cutoff:
                os.remove(path)

