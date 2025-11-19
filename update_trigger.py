import subprocess
import time
import logging

logging.basicConfig(
    filename="update_trigger.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logging.info("Waiting for FlaskAPI to exit...")
time.sleep(3)  # Give Flask a moment to shut down

logging.info("Stopping FlaskAPI...")
subprocess.run(["sc", "stop", "FlaskAPI"], check=False)
time.sleep(5)

logging.info("Starting FlaskAPI...")
subprocess.run(["sc", "start", "FlaskAPI"], check=False)

logging.info("Restart complete.")
