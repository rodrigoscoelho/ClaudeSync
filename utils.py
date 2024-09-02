from datetime import datetime
from config_logging import logger, claude_provider

def create_new_chat(organization_id, project_id):
    chat_name = f"#claudesync - {datetime.now().strftime('%H:%M:%S')}"
    chat = claude_provider.create_chat(organization_id, project_uuid=project_id, chat_name=chat_name)
    logger.info(f"Created new chat with ID: {chat['uuid']} and name: {chat_name}")
    return chat['uuid']