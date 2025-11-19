import subprocess
import time
import logging

SC_EXE = r"C:\Windows\System32\sc.exe"

logging.basicConfig(
    filename="update_trigger.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

logging.info("Waiting for FlaskAPI to exit...")
time.sleep(3)

logging.info("Stopping FlaskAPI...")
subprocess.run([SC_EXE, "stop", "FlaskAPI"], check=False)
time.sleep(5)

logging.info("Starting FlaskAPI...")
subprocess.run([SC_EXE, "start", "FlaskAPI"], check=False)

logging.info("Restart complete.")
