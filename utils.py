import logging
import os
import sys

def setup_logging(log_dir: str, log_file_name: str = 'youtube_download.log'):
    """Configures logging to stream and file."""
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
        except OSError as e:
            print(f"Error creating log directory {log_dir}: {e}", file=sys.stderr)
            # Fallback to current directory if log_dir creation fails
            log_dir = "."
            print(f"Logging to current directory instead.", file=sys.stderr)

    log_file_path = os.path.join(log_dir, log_file_name)

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout), # Log to stdout
            logging.FileHandler(log_file_path)
        ]
    )
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured. Log file: {log_file_path}")
    return logger
