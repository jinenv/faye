# src/utils/logger.py
import logging
from logging.handlers import RotatingFileHandler
import os

def get_logger(name):
    """
    Configures and returns a general-purpose logger.
    Logs to console and a rotating file (bot.log).
    """
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO) 

    # Prevent adding handlers multiple times
    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

        # General File Handler (bot.log)
        log_file_path = os.path.join(log_dir, 'bot.log')
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=1024 * 1024 * 5, # 5 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


# --- NEW DEDICATED TRANSACTION LOGGER ---
def get_transaction_logger():
    """
    Configures and returns a logger specifically for transactional events.
    Logs ONLY to a dedicated file (transactions.log).
    """
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)

    # Use a fixed name to get the same logger instance every time this is called
    tx_logger = logging.getLogger("transaction_audit")
    tx_logger.setLevel(logging.INFO)
    
    # This is crucial: it prevents the transaction logs from also being sent to the console/bot.log
    tx_logger.propagate = False

    # Add a handler ONLY if one for this specific file doesn't already exist
    if not any(isinstance(h, RotatingFileHandler) and 'transactions.log' in h.baseFilename for h in tx_logger.handlers):
        log_file_path = os.path.join(log_dir, 'transactions.log')
        tx_file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=1024 * 1024 * 10, # 10 MB (transactions can be numerous)
            backupCount=10,
            encoding='utf-8'
        )
        tx_file_handler.setLevel(logging.INFO)
        # Use a simpler format for the transaction log for better readability
        tx_formatter = logging.Formatter('%(asctime)s | %(message)s')
        tx_file_handler.setFormatter(tx_formatter)
        tx_logger.addHandler(tx_file_handler)

    return tx_logger