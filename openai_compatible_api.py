import sys
import os
import json
import logging
from flask import Flask, request, jsonify

# Add the src directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.join(current_dir, 'src')
sys.path.append(src_dir)

from claudesync.providers.claude_ai import ClaudeAIProvider
from claudesync.exceptions import ProviderError
from claudesync.config_manager import ConfigManager

app = Flask(__name__)

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize the ConfigManager and ClaudeAIProvider
config = ConfigManager()
try:
    claude_provider = ClaudeAIProvider(config)
except Exception as e:
    logger.error(f"Failed to initialize ClaudeAIProvider: {str(e)}")
    claude_provider = None

@app.route('/v1/chat/completions', methods=['POST'])
def chat_completions():
    if claude_provider is None:
        return jsonify({'error': 'ClaudeAIProvider is not initialized'}), 500

    try:
        # Get the request data
        data = request.json
        logger.debug(f"Received request data: {data}")

        # Extract relevant information from the OpenAI-style request
        messages = data.get('messages', [])
        max_tokens = data.get('max_tokens', 1000)  # Default to 1000 if not specified

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

        # Send the request to Claude.ai
        conversation_id = None  # We're starting a new conversation each time
        response = claude_provider.send_message(conversation_id, prompt)
        logger.debug(f"Received response from Claude.ai: {response}")

        # Convert Claude.ai response to OpenAI-style response
        openai_response = {
            'id': f"chatcmpl-{response.get('id', 'unknown')}",
            'object': 'chat.completion',
            'created': response.get('created', 0),
            'model': 'claude-2',  # Assuming Claude 2 model
            'choices': [
                {
                    'index': 0,
                    'message': {
                        'role': 'assistant',
                        'content': response.get('content', ''),
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

        logger.debug(f"Returning OpenAI-style response: {openai_response}")
        return jsonify(openai_response)

    except ProviderError as e:
        logger.error(f"ProviderError occurred: {str(e)}")
        return jsonify({'error': str(e)}), 500
    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}", exc_info=True)
        return jsonify({'error': f'Unexpected error: {str(e)}'}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)