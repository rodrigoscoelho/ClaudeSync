from flask import request, jsonify, render_template_string
from config_logging import logger, config, claude_provider
from datetime import datetime, timedelta
import os

def register_auth_routes(app):
    @app.before_request
    def check_auth():
        logger.info(f"Received request: {request.method} {request.url}")
        logger.info(f"Request headers: {request.headers}")
        
        if request.method == 'OPTIONS':
            return '', 204
        
        if request.endpoint not in ['login', 'config', 'index', 'check_login']:
            session_key, _ = config.get_session_key("claude.ai")
            logger.debug(f"Retrieved session key: {'[REDACTED]' if session_key else 'None'}")
            if not session_key:
                logger.error("Not authenticated")
                return jsonify({'error': 'Not authenticated. Please log in first.'}), 401

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
                logger.error("No session key provided in login attempt")
                return jsonify({'error': 'No session key provided'}), 400

            try:
                logger.info("Attempting to log in to Claude.ai with provided session key")
                expiry = datetime.now() + timedelta(hours=24)  # Set expiry to 24 hours from now
                config.set_session_key("claude.ai", session_key, expiry)
                
                # Verify that the session key was saved correctly
                key_file_path = os.path.join(config.global_config_dir, "claude.ai.key")
                if not os.path.exists(key_file_path):
                    logger.error(f"Session key file not created at {key_file_path}")
                    return jsonify({'error': 'Failed to save session key'}), 500

                # Verify the login by trying to get organizations
                try:
                    organizations = claude_provider.get_organizations()
                    if organizations:
                        logger.info(f"Successfully logged in and retrieved {len(organizations)} organizations")
                        # Set the first organization as the active one
                        active_org = organizations[0]
                        config.set("active_organization_id", active_org['id'])
                        logger.info(f"Set active organization: {active_org['name']} (ID: {active_org['id']})")
                        return jsonify({
                            'message': 'Successfully logged in to Claude.ai',
                            'organizations_count': len(organizations),
                            'active_organization': active_org['name']
                        }), 200
                    else:
                        logger.error("Failed to retrieve organizations after login")
                        return jsonify({'error': 'Login failed: Unable to retrieve organizations'}), 401
                except Exception as e:
                    logger.error(f"Failed to verify login: {str(e)}")
                    return jsonify({'error': f'Login failed: {str(e)}'}), 401
            except Exception as e:
                logger.error(f"Unexpected error during login: {str(e)}", exc_info=True)
                return jsonify({'error': f'Unexpected error during login: {str(e)}'}), 500

    @app.route('/check_login', methods=['GET'])
    def check_login():
        session_key, _ = config.get_session_key("claude.ai")
        if not session_key:
            logger.error("No session key found during login check")
            return jsonify({'status': 'Not logged in'}), 401
        
        try:
            organizations = claude_provider.get_organizations()
            if organizations:
                logger.info(f"Login check successful. Retrieved {len(organizations)} organizations")
                active_org_id = config.get("active_organization_id")
                if not active_org_id:
                    # Set the first organization as the active one if not set
                    active_org = organizations[0]
                    config.set("active_organization_id", active_org['id'])
                    logger.info(f"Set active organization: {active_org['name']} (ID: {active_org['id']})")
                else:
                    active_org = next((org for org in organizations if org['id'] == active_org_id), None)
                    if not active_org:
                        logger.warning(f"Active organization with ID {active_org_id} not found. Setting first organization as active.")
                        active_org = organizations[0]
                        config.set("active_organization_id", active_org['id'])
                return jsonify({
                    'status': 'Logged in',
                    'organizations_count': len(organizations),
                    'active_organization': active_org['name']
                }), 200
            else:
                logger.error("Failed to retrieve organizations during login check")
                return jsonify({'status': 'Error', 'message': 'Unable to verify login status'}), 500
        except Exception as e:
            logger.error(f"Error checking login status: {str(e)}", exc_info=True)
            return jsonify({'status': 'Error', 'message': str(e)}), 500

    @app.route('/config', methods=['GET', 'POST'])
    def config_page():
        if request.method == 'POST':
            new_cookie = request.form.get('cookie')
            if new_cookie:
                expiry = datetime.now() + timedelta(hours=24)  # Set expiry to 24 hours from now
                config.set_session_key("claude.ai", new_cookie, expiry)
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