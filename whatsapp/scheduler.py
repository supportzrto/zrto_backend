import threading
import time
from database import SessionLocal
from whatsapp import config
from whatsapp.service import process_pending_orders

_started = False
_lock = threading.Lock()

def _run_sweep():
    db = SessionLocal()
    try: process_pending_orders(db)
    finally: db.close()

def _thread_loop():
    while True:
        _run_sweep()
        time.sleep(config.SCHEDULER_INTERVAL_SECONDS)

def start_scheduler():
    global _started
    with _lock:
        if _started: return
        _started = True
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        scheduler = BackgroundScheduler(daemon=True)
        scheduler.add_job(_run_sweep, "interval", seconds=config.SCHEDULER_INTERVAL_SECONDS)
        scheduler.start()
    except Exception:
        threading.Thread(target=_thread_loop, daemon=True).start()