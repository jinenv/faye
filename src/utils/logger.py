# src/utils/logger.py
import logging
from logging.handlers import RotatingFileHandler
import os

def get_logger(name):
    """
    Configures and returns a logger instance.
    Logs to console and a rotating file.
    """
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True) # Ensure logs directory exists

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO) # Set default logging level

    # Prevent adding handlers multiple times if get_logger is called repeatedly
    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # File Handler (Rotating)
        log_file_path = os.path.join(log_dir, 'bot.log')
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=1024 * 1024 * 5, # 5 MB
            backupCount=5 # Keep 5 backup logs
        )
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger