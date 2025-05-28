import logging
import os
from logging.handlers import RotatingFileHandler

# --- Configuration for Logging ---
LOG_DIR = "logs"
LOG_FILE = "bot.log"
MAX_BYTES = 5 * 1024 * 1024 # 5 MB
BACKUP_COUNT = 5 # Keep up to 5 backup log files
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_LEVEL = logging.INFO # Set default logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

class Logger:
    """
    A custom Logger class to provide standardized logging for Project X.
    Logs messages to console and to a rotating file.
    """
    _initialized = False # Class-level flag to ensure setup runs only once
    _loggers = {} # Cache for specific named loggers

    def __new__(cls, name: str = "main"):
        """
        Ensures a specific named logger is returned (or created).
        Sets up the root logger configuration only once.
        """
        if name not in cls._loggers:
            # Get the logger instance for the given name
            logger = logging.getLogger(name)
            logger.setLevel(LOG_LEVEL)
            logger.propagate = False # Prevent messages from being sent to ancestor loggers (and thus stdout multiple times)

            # Ensure handlers are not duplicated if setup is called multiple times (e.g., by different cogs)
            if not logger.handlers:
                # Create formatter
                formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)

                # Console Handler
                console_handler = logging.StreamHandler()
                console_handler.setFormatter(formatter)
                logger.addHandler(console_handler)

                # File Handler (rotating)
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

# Example usage (for internal testing of this module if needed, otherwise ignored)
if __name__ == '__main__':
    test_log = Logger("test_module")
    test_log.info("This is an info message from the test module.")
    test_log.warning("This is a warning message.")
    test_log.error("This is an error message.")
    test_log.debug("This is a debug message (won't show unless LOG_LEVEL is DEBUG).")