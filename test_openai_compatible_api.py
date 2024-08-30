import requests
import json
import logging

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_chat_completion():
    url = "http://localhost:5000/v1/chat/completions"
    
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "model": "claude-2",  # This is ignored by our API but included for OpenAI compatibility
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "What is the capital of France?"}
        ],
        "max_tokens": 150
    }
    
    try:
        logger.debug(f"Sending request to {url}")
        logger.debug(f"Request headers: {headers}")
        logger.debug(f"Request data: {json.dumps(data, indent=2)}")
        
        response = requests.post(url, headers=headers, data=json.dumps(data))
        
        logger.debug(f"Response status code: {response.status_code}")
        logger.debug(f"Response headers: {dict(response.headers)}")
        
        try:
            result = response.json()
            logger.debug(f"Response content: {json.dumps(result, indent=2)}")
            
            if 'choices' in result and len(result['choices']) > 0:
                print("\nAssistant's response:")
                print(result['choices'][0]['message']['content'])
            elif 'error' in result:
                print(f"\nError returned by API: {result['error']}")
            else:
                print("\nUnexpected response structure:")
                print(json.dumps(result, indent=2))
        
        except json.JSONDecodeError:
            logger.error("Failed to decode the API response as JSON")
            logger.error(f"Raw response content: {response.text}")
        
    except requests.exceptions.RequestException as e:
        logger.error(f"An error occurred while making the request: {e}")

if __name__ == "__main__":
    test_chat_completion()