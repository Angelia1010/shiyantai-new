import logging
import os
from datetime import datetime

LOG_DIR = os.path.dirname(os.path.abspath(__file__))

def setup_logger(service_name, log_level=logging.INFO):
    logger = logging.getLogger(service_name)
    logger.setLevel(log_level)
    
    if logger.handlers:
        return logger
    
    today = datetime.now().strftime('%Y-%m-%d')
    log_file = os.path.join(LOG_DIR, f'{service_name}_{today}.log')
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(log_level)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger

def log_frontend_message(message, level='info', source='frontend'):
    today = datetime.now().strftime('%Y-%m-%d')
    log_file = os.path.join(LOG_DIR, f'frontend_{today}.log')
    
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f'{timestamp} - {source} - {level.upper()} - {message}\n'
    
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(log_entry)
    
    return True
