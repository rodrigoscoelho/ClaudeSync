import logging
import os
from claudesync.configmanager.file_config_manager import FileConfigManager
from claudesync.providers.claude_ai import ClaudeAIProvider

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Add a file handler to log to a file
log_dir = '/var/log/claude_openai_api'
if not os.path.exists(log_dir):
    os.makedirs(log_dir, exist_ok=True)
file_handler = logging.FileHandler(os.path.join(log_dir, 'claude_openai_api.log'))
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