import getpass
import os

import logging
logger = logging.getLogger(__name__)

def _set_env(var: str):
    logger.info(f"Setting {var} environment variable...")
    if not os.environ.get(var):
        os.environ[var] = getpass.getpass(f"{var}: ")
