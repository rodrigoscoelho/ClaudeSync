#!/usr/bin/env python3

import os
import sys
import argparse
from flask import Flask
from flask_cors import CORS
import ssl

# Add the src directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.append(src_dir)

from config_logging import logger, config, initialize_claude_provider
from api_routes import register_api_routes
from auth_routes import register_auth_routes

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Register routes
register_api_routes(app)
register_auth_routes(app)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run Claude OpenAI API server')
    parser.add_argument('--use-ssl', action='store_true', help='Use SSL for HTTPS connections')
    args = parser.parse_args()

    if args.use_ssl:
        cert_file = 'cert.pem'
        key_file = 'key.pem'
        
        if os.path.exists(cert_file) and os.path.exists(key_file):
            # Create SSL context
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(certfile=cert_file, keyfile=key_file)
            
            # Run the app with SSL
            logger.info("Running in HTTPS mode.")
            app.run(debug=True, host='0.0.0.0', port=5001, threaded=True, ssl_context=ssl_context)
        else:
            logger.error("SSL certificate files not found. Please make sure cert.pem and key.pem are present.")
            sys.exit(1)
    else:
        # Run the app without SSL
        logger.info("Running in HTTP mode.")
        app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)
