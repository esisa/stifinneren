import os, sys
sys.path.insert(0, os.path.dirname(__file__))
print os.path.dirname(__file__) + "/stifinneren"

import logging
logging.basicConfig()

from stifinnern.app import app as application

