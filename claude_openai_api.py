import os
import sys
import json
import logging
import argparse
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.exceptions import BadRequest, UnsupportedMediaType
from datetime import datetime
import ssl

# Add the src directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.append(src_dir)

from claudesync.providers.claude_ai import ClaudeAIProvider
from claudesync.exceptions import ProviderError
from claudesync.configmanager.file_config_manager import FileConfigManager

app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add a file handler to log to a file
file_handler = logging.FileHandler('claude_openai_api.log')
file_handler.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

# Initialize the ConfigManager and ClaudeAIProvider
config = FileConfigManager()
try:
    claude_provider = ClaudeAIProvider(config)
except Exception as e:
    logger.error(f"Failed to initialize ClaudeAIProvider: {str(e)}")
    claude_provider = None

def create_new_chat(organization_id, project_id):
    chat_name = f"#claudesync - {datetime.now().strftime('%H:%M:%S')}"
    chat = claude_provider.create_chat(organization_id, project_uuid=project_id, chat_name=chat_name)
    logger.info(f"Created new chat with ID: {chat['uuid']} and name: {chat_name}")
    return chat['uuid']

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def chat_completions():
    logger.info(f"Received request: {request.method} {request.url}")
    logger.info(f"Request headers: {request.headers}")
    
    if request.method == 'OPTIONS':
        return '', 204
    
    if claude_provider is None:
        logger.error("ClaudeAIProvider is not initialized")
        return jsonify({'error': 'ClaudeAIProvider is not initialized'}), 500

    if request.content_type != 'application/json':
        logger.error(f"Unsupported Media Type: {request.content_type}")
        return jsonify({'error': 'Unsupported Media Type: Content-Type must be application/json'}), 415

    try:
        # Get the request data
        data = request.get_json(force=True)
        if data is None:
            logger.error("Invalid JSON data")
            raise BadRequest("Invalid JSON data")
        
        logger.info(f"Received request data: {data}")

        # Extract relevant information from the OpenAI-style request
        messages = data.get('messages', [])
        max_tokens = data.get('max_tokens', 1000)  # Default to 1000 if not specified
        model = data.get('model', 'claude-3.5-sonnet')  # Default to claude-3.5-sonnet if not specified

        # Convert OpenAI-style messages to Claude.ai format
        claude_messages = []
        for message in messages:
            role = message['role']
            content = message['content']
            if role == 'system':
                claude_messages.append({'role': 'Human', 'content': f"System: {content}"})
            elif role == 'user':
                claude_messages.append({'role': 'Human', 'content': content})
            elif role == 'assistant':
                claude_messages.append({'role': 'Assistant', 'content': content})

        logger.debug(f"Converted messages: {claude_messages}")

        # Prepare the prompt for Claude.ai
        prompt = "\n".join([f"{msg['role']}: {msg['content']}" for msg in claude_messages])

        # Get the active organization and project
        organization_id = config.get("active_organization_id")
        project_id = config.get("active_project_id")

        if not organization_id:
            logger.error("No active organization set")
            return jsonify({'error': 'No active organization set'}), 400

        # Check if a chat ID is provided in the header
        chat_id = request.headers.get('X-Claude-Chat-Id')
        
        if chat_id:
            logger.info(f"Using existing chat with ID: {chat_id}")
        else:
            # Create a new chat with the specified naming convention
            chat_id = create_new_chat(organization_id, project_id)

        # Send the message and get the response
        response_content = ""
        for event in claude_provider.send_message(organization_id, chat_id, prompt):
            if "completion" in event:
                response_content += event["completion"]
            elif "content" in event:
                response_content += event["content"]
            elif "error" in event:
                logger.error(f"Error in Claude.ai response: {event['error']}")
                raise ProviderError(f"Error in Claude.ai response: {event['error']}")

        # Convert Claude.ai response to OpenAI-style response
        openai_response = {
            'id': f"chatcmpl-{chat_id}",
            'object': 'chat.completion',
            'created': int(datetime.now().timestamp()),  # Use current timestamp
            'model': model,  # Use the model specified in the request or the default
            'choices': [
                {
                    'index': 0,
                    'message': {
                        'role': 'assistant',
                        'content': response_content,
                    },
                    'finish_reason': 'stop',
                }
            ],
            'usage': {
                'prompt_tokens': -1,  # Claude.ai doesn't provide this information
                'completion_tokens': -1,  # Claude.ai doesn't provide this information
                'total_tokens': -1,  # Claude.ai doesn't provide this information
            }
        }

        logger.info(f"Returning OpenAI-style response: {openai_response}")
        return jsonify(openai_response)

    except ProviderError as e:
        logger.error(f"ProviderError occurred: {str(e)}")
        return jsonify({'error': str(e)}), 500
    except BadRequest as e:
        logger.error(f"Bad request: {str(e)}")
        return jsonify({'error': str(e)}), 400
    except UnsupportedMediaType as e:
        logger.error(f"Unsupported Media Type: {str(e)}")
        return jsonify({'error': str(e)}), 415
    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}", exc_info=True)
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

@app.route('/v1/models', methods=['GET'])
def list_models():
    models = [
        {
            "id": "claude-3.5-sonnet",
            "object": "model",
            "created": 1686935002,
            "owned_by": "anthropic"
        },
        {
            "id": "claude-2",
            "object": "model",
            "created": 1686935002,
            "owned_by": "anthropic"
        }
    ]
    return jsonify({"object": "list", "data": models})

@app.before_request
def check_auth():
    logger.info(f"Received request: {request.method} {request.url}")
    logger.info(f"Request headers: {request.headers}")
    
    if request.method == 'OPTIONS':
        return '', 204
    
    if request.endpoint != 'login':
        session_key, _ = config.get_session_key("claude.ai")
        if not session_key:
            logger.error("Not authenticated")
            return jsonify({'error': 'Not authenticated. Please log in first.'}), 401

@app.route('/login', methods=['POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        session_key, expiry = claude_provider.login()
        config.set_session_key("claude.ai", session_key, expiry)
        logger.info("Successfully logged in to Claude.ai")
        return jsonify({'message': 'Successfully logged in to Claude.ai'}), 200
    except ProviderError as e:
        logger.error(f"Login failed: {str(e)}")
        return jsonify({'error': f'Login failed: {str(e)}'}), 401

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
            print("Running in HTTPS mode.")
            app.run(debug=True, port=5000, threaded=True, ssl_context=ssl_context)
        else:
            print("SSL certificate files not found. Please make sure cert.pem and key.pem are present.")
            sys.exit(1)
    else:
        # Run the app without SSL
        print("Running in HTTP mode.")
        app.run(debug=True, port=5000, threaded=True)