#!/usr/bin/env python3

import os
import sys
import json
import logging
import argparse
from flask import Flask, request, jsonify, render_template_string, redirect, url_for
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
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Initialize the ConfigManager and ClaudeAIProvider
config = FileConfigManager()
try:
    claude_provider = ClaudeAIProvider(config)
    logger.info("ClaudeAIProvider initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize ClaudeAIProvider: {str(e)}")
    claude_provider = None

def create_new_chat(organization_id, project_id):
    chat_name = f"#claudesync - {datetime.now().strftime('%H:%M:%S')}"
    chat = claude_provider.create_chat(organization_id, project_uuid=project_id, chat_name=chat_name)
    logger.info(f"Created new chat with ID: {chat['uuid']} and name: {chat_name}")
    return chat['uuid']

@app.route('/', methods=['GET'])
def index():
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Claude.ai API</title>
        </head>
        <body>
            <h1>Claude.ai API</h1>
            <a href="/login">Login to Claude.ai</a><br>
            <a href="/check_login">Check Login Status</a><br>
            <h2>ClaudeSync Options</h2>
            <button onclick="location.href='/list_chats'">List Chats</button>
            <button onclick="location.href='/list_projects'">List Projects</button>
            <button onclick="location.href='/list_organizations'">List Organizations</button>
            <h2>Test API</h2>
            <button onclick="location.href='/test_api'">Test API</button>
        </body>
        </html>
    ''')

@app.route('/v1/chat/completions', methods=['POST', 'OPTIONS'])
def chat_completions():
    logger.info(f"Received request: {request.method} {request.url}")
    logger.info(f"Request headers: {json.dumps(dict(request.headers), indent=2)}")
    
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
        
        logger.info(f"Received request data: {json.dumps(data, indent=2)}")

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

        logger.debug(f"Converted messages: {json.dumps(claude_messages, indent=2)}")

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

        logger.info(f"Sending request to Claude.ai API:")
        logger.info(f"Organization ID: {organization_id}")
        logger.info(f"Chat ID: {chat_id}")
        logger.info(f"Prompt: {prompt}")

        # Send the message and get the response
        response_content = ""
        for event in claude_provider.send_message(organization_id, chat_id, prompt):
            logger.debug(f"Received event from Claude.ai: {json.dumps(event, indent=2)}")
            if "completion" in event:
                response_content += event["completion"]
            elif "content" in event:
                response_content += event["content"]
            elif "error" in event:
                logger.error(f"Error in Claude.ai response: {event['error']}")
                raise ProviderError(f"Error in Claude.ai response: {event['error']}")

        logger.info(f"Full response from Claude.ai: {response_content}")

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

        logger.info(f"Returning OpenAI-style response: {json.dumps(openai_response, indent=2)}")
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
    logger.info(f"Request headers: {json.dumps(dict(request.headers), indent=2)}")
    
    if request.method == 'OPTIONS':
        return '', 204
    
    if request.endpoint not in ['login', 'config', 'index', 'check_login']:
        session_key, _ = config.get_session_key("claude.ai")
        logger.debug(f"Retrieved session key: {'[REDACTED]' if session_key else 'None'}")
        if not session_key:
            logger.error("Not authenticated")
            return jsonify({'error': 'Not authenticated. Please log in first.'}), 401

@app.route('/login', methods=['GET', 'POST', 'OPTIONS'])
def login():
    if request.method == 'OPTIONS':
        return '', 204
    
    if request.method == 'GET':
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Login to Claude.ai</title>
            </head>
            <body>
                <h1>Login to Claude.ai</h1>
                <form method="POST">
                    <label for="session_key">Enter your Claude.ai session key:</label><br>
                    <input type="text" id="session_key" name="session_key" required><br><br>
                    <input type="submit" value="Login">
                </form>
            </body>
            </html>
        ''')
    
    if request.method == 'POST':
        session_key = request.form.get('session_key')
        if not session_key:
            return jsonify({'error': 'No session key provided'}), 400

        try:
            logger.info("Attempting to log in to Claude.ai with provided session key")
            config.set_session_key("claude.ai", session_key, None)  # Set expiry to None as it's a manual entry
            
            # Verify the login by trying to get the active organization
            try:
                organization_id = config.get("active_organization_id")
                if organization_id:
                    logger.info(f"Successfully logged in and retrieved active organization ID: {organization_id}")
                    return jsonify({'message': 'Successfully logged in to Claude.ai', 'organization_id': organization_id}), 200
                else:
                    logger.error("Failed to retrieve active organization ID after login")
                    return jsonify({'error': 'Login failed: Unable to retrieve active organization ID'}), 401
            except Exception as e:
                logger.error(f"Failed to retrieve active organization ID after login: {str(e)}")
                return jsonify({'error': 'Login failed: Unable to retrieve active organization ID'}), 401
        except Exception as e:
            logger.error(f"Unexpected error during login: {str(e)}", exc_info=True)
            return jsonify({'error': f'Unexpected error during login: {str(e)}'}), 500

@app.route('/check_login', methods=['GET'])
def check_login():
    session_key, _ = config.get_session_key("claude.ai")
    if not session_key:
        return jsonify({'status': 'Not logged in'}), 401
    
    try:
        organization_id = config.get("active_organization_id")
        if organization_id:
            return jsonify({'status': 'Logged in', 'organization_id': organization_id}), 200
        else:
            return jsonify({'status': 'Error', 'message': 'No active organization set'}), 500
    except Exception as e:
        logger.error(f"Error checking login status: {str(e)}")
        return jsonify({'status': 'Error', 'message': str(e)}), 500

@app.route('/list_chats', methods=['GET'])
def list_chats():
    try:
        organization_id = config.get("active_organization_id")
        if not organization_id:
            return jsonify({'error': 'No active organization set'}), 400

        chats = claude_provider.get_chat_conversations(organization_id)
        
        if not chats:
            logger.info("No chats found. Creating a new chat.")
            new_chat_id = create_new_chat(organization_id, None)
            chats = claude_provider.get_chat_conversations(organization_id)
        
        return jsonify(chats), 200
    except Exception as e:
        logger.error(f"Error listing chats: {str(e)}")
        return jsonify({'error': f'Error listing chats: {str(e)}'}), 500

@app.route('/list_projects', methods=['GET'])
def list_projects():
    try:
        logger.info("Attempting to list projects")
        session_key, _ = config.get_session_key("claude.ai")
        if not session_key:
            logger.error("Not authenticated")
            return jsonify({'error': 'Not authenticated. Please log in first.'}), 401
        
        logger.info("Using session key to list projects")
        projects = claude_provider.get_projects()
        
        if not projects:
            logger.info("No projects found.")
            return jsonify([]), 200
        
        logger.info(f"Successfully retrieved projects: {json.dumps(projects, indent=2)}")
        return jsonify(projects), 200
    except ProviderError as e:
        logger.error(f"ProviderError occurred while listing projects: {str(e)}")
        return jsonify({'error': f'Error listing projects: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Unexpected error occurred while listing projects: {str(e)}", exc_info=True)
        return jsonify({'error': f'Unexpected error listing projects: {str(e)}'}), 500

@app.route('/list_organizations', methods=['GET'])
def list_organizations():
    try:
        organizations = claude_provider.get_organizations()
        return jsonify(organizations), 200
    except Exception as e:
        logger.error(f"Error listing organizations: {str(e)}")
        return jsonify({'error': f'Error listing organizations: {str(e)}'}), 500

@app.route('/config', methods=['GET', 'POST'])
def config_page():
    if request.method == 'POST':
        new_cookie = request.form.get('cookie')
        if new_cookie:
            config.set_session_key("claude.ai", new_cookie, None)  # Set expiry to None as it's a manual entry
            logger.info("Successfully updated Claude.ai cookie")
            return jsonify({'message': 'Cookie updated successfully'}), 200
        else:
            return jsonify({'error': 'No cookie provided'}), 400

    # If it's a GET request, render the configuration page
    return render_template_string('''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Claude.ai Configuration</title>
        </head>
        <body>
            <h1>Claude.ai Configuration</h1>
            <form method="POST">
                <label for="cookie">Enter new Claude.ai cookie:</label><br>
                <input type="text" id="cookie" name="cookie" size="50"><br>
                <input type="submit" value="Update Cookie">
            </form>
        </body>
        </html>
    ''')

@app.route('/test_api', methods=['GET', 'POST'])
def test_api():
    if request.method == 'GET':
        return render_template_string('''
            <!DOCTYPE html>
            <html>
            <head>
                <title>Test Claude.ai API</title>
            </head>
            <body>
                <h1>Test Claude.ai API</h1>
                <form method="POST">
                    <input type="submit" value="Test API">
                </form>
            </body>
            </html>
        ''')
    
    if request.method == 'POST':
        try:
            logger.info("Starting API test")
            organization_id = config.get("active_organization_id")
            if not organization_id:
                logger.error("No active organization set")
                return jsonify({'error': 'No active organization set'}), 400

            logger.info(f"Using organization ID: {organization_id}")
            
            # Check if there are any existing projects
            projects = claude_provider.get_projects()
            if not projects:
                logger.info("No projects found. Creating a new project.")
                new_project = claude_provider.create_project("Test Project", "Created for API test")
                projects = claude_provider.get_projects()
            
            project_id = projects[0]['id']
            logger.info(f"Using project ID: {project_id}")
            
            prompt = "Rodrigo é o maior, Rodrigo Coelho é demais, quem é o maioral?"
            logger.info(f"Creating new chat with prompt: {prompt}")
            
            try:
                chat_id = create_new_chat(organization_id, project_id)
                logger.info(f"Created new chat with ID: {chat_id}")
            except Exception as e:
                logger.error(f"Error creating new chat: {str(e)}")
                return jsonify({'error': f'Error creating new chat: {str(e)}'}), 500
            
            logger.info("Sending message to Claude.ai")
            response_content = ""
            try:
                for event in claude_provider.send_message(organization_id, chat_id, prompt):
                    logger.debug(f"Received event: {json.dumps(event, indent=2)}")
                    if "completion" in event:
                        response_content += event["completion"]
                    elif "content" in event:
                        response_content += event["content"]
                    elif "error" in event:
                        raise ProviderError(f"Error in Claude.ai response: {event['error']}")
            except Exception as e:
                logger.error(f"Error sending message to Claude.ai: {str(e)}")
                return jsonify({'error': f'Error sending message to Claude.ai: {str(e)}'}), 500

            logger.info(f"Received response from Claude.ai: {response_content}")
            return jsonify({'response': response_content}), 200
        except Exception as e:
            logger.error(f"Unexpected error during API test: {str(e)}", exc_info=True)
            return jsonify({'error': f'Unexpected error during API test: {str(e)}'}), 500

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
            app.run(debug=True, host='0.0.0.0', port=5001, threaded=True, ssl_context=ssl_context)
        else:
            print("SSL certificate files not found. Please make sure cert.pem and key.pem are present.")
            sys.exit(1)
    else:
        # Run the app without SSL
        print("Running in HTTP mode.")
        app.run(debug=True, host='0.0.0.0', port=5001, threaded=True)