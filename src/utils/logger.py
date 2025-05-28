import logging
import os
from logging.handlers import RotatingFileHandler

# --- Configuration for Logging ---
LOG_DIR = "logs" # Folder where logs will be stored
LOG_FILE = "bot.log"
MAX_BYTES = 5 * 1024 * 1024 # 5 MB per log file
BACKUP_COUNT = 5 # Keep up to 5 backup log files (e.g., bot.log.1, bot.log.2, etc.)
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = logging.INFO # Default logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

class Logger:
    """
    A custom Logger class to provide standardized logging for Nyxa Bot.
    Logs messages to console and to a rotating file.
    """
    _loggers = {} # Cache for specific named loggers to prevent duplication

    def __new__(cls, name: str = "main"):
        """
        Ensures a specific named logger is returned (or created) for each module.
        Sets up the logger configuration with handlers if it's the first time
        this named logger is requested.
        """
        if name not in cls._loggers:
            # Get the logger instance for the given name
            logger = logging.getLogger(name)
            logger.setLevel(LOG_LEVEL)
            logger.propagate = False # Prevent messages from being sent to ancestor loggers

            # Add handlers only if they haven't been added already
            if not logger.handlers:
                # Create formatter
                formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

                # Console Handler: Logs to standard output (your terminal)
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)

                # File Handler (rotating): Logs to a file, rotates when maxBytes is reached
                # Ensure log directory exists
                if not os.path.exists(LOG_DIR):
                    os.makedirs(LOG_DIR)
                file_handler = RotatingFileHandler(
                    os.path.join(LOG_DIR, LOG_FILE),
                    maxBytes=MAX_BYTES,
                    backupCount=BACKUP_COUNT,
                    encoding='utf-8'
                )
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)

            cls._loggers[name] = logger
        return cls._loggers[name]