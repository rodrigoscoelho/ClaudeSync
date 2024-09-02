import json
from flask import request, jsonify, render_template_string
from werkzeug.exceptions import BadRequest, UnsupportedMediaType
from datetime import datetime
from claudesync.exceptions import ProviderError
from config_logging import logger, config, claude_provider
from utils import create_new_chat

def create_default_project(organization_id):
    """Creates a default project if no projects exist."""
    try:
        project_name = "Default ClaudeSync Project"
        project_description = "Default project created automatically by ClaudeSync"
        new_project = claude_provider.create_project(organization_id, project_name, project_description)
        logger.info(f"Created default project: {json.dumps(new_project, indent=2)}")
        return [new_project]
    except Exception as e:
        logger.error(f"Error creating default project: {str(e)}")
        raise

def register_api_routes(app):
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
            
            organization_id = config.get("active_organization_id")
            if not organization_id:
                logger.error("No active organization set")
                return jsonify({'error': 'No active organization set'}), 400
            
            logger.info(f"Using organization ID: {organization_id}")
            logger.info(f"Session key (first 10 characters): {session_key[:10]}...")
            
            # Log the API URL being used
            api_url = config.get("claude_api_url", "https://api.claude.ai/api")
            logger.info(f"Using API URL: {api_url}")
            
            # Attempt to get organizations to verify the session key
            try:
                organizations = claude_provider.get_organizations()
                logger.info(f"Successfully retrieved organizations: {json.dumps(organizations, indent=2)}")
            except Exception as org_error:
                logger.error(f"Failed to retrieve organizations: {str(org_error)}")
                return jsonify({'error': f'Failed to verify session key: {str(org_error)}'}), 401
            
            try:
                projects = claude_provider.get_projects(organization_id)
                
                if not projects:
                    logger.info("No projects found. Creating a default project.")
                    projects = create_default_project(organization_id)
                
                logger.info(f"Successfully retrieved projects: {json.dumps(projects, indent=2)}")
                return jsonify(projects), 200
            except ProviderError as e:
                if "404" in str(e):
                    logger.warning(f"No projects found for organization {organization_id}. Creating a default project.")
                    projects = create_default_project(organization_id)
                    return jsonify(projects), 200
                else:
                    raise
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
                try:
                    projects = claude_provider.get_projects(organization_id)
                    if not projects:
                        logger.info("No projects found. Creating a new project.")
                        projects = create_default_project(organization_id)
                except ProviderError as e:
                    if "404" in str(e):
                        logger.info("No projects found. Creating a new project.")
                        projects = create_default_project(organization_id)
                    else:
                        raise

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