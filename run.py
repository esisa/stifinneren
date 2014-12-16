import logging
logging.basicConfig()

from stifinneren.app import app

if __name__ == '__main__':
    app.run(app.run(host='0.0.0.0',port=5000))
