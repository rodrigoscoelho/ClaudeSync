import urllib.request
import urllib.error
import urllib.parse
import json
import gzip
from datetime import datetime, timezone

from claudesync.providers.base_claude_ai import BaseClaudeAIProvider
from claudesync.exceptions import ProviderError
from claudesync.configmanager.inmemory_config_manager import InMemoryConfigManager

class ClaudeAIProvider(BaseClaudeAIProvider):
    def __init__(self, config=None):
        if config is None:
            config = InMemoryConfigManager()
        config.set("claude_api_url", "https://api.claude.ai/api")
        super().__init__(config)
        # No need to set self.base_url directly

    def _make_request(self, method, endpoint, data=None, headers=None):
        url = f"{self.base_url}{endpoint}"
        default_headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept-Encoding": "gzip",
        }

        if headers:
            default_headers.update(headers)

        session_key, expiry = self.config.get_session_key("claude.ai")
        cookies = {
            "sessionKey": session_key,
        }

        try:
            self.logger.debug(f"Making {method} request to {url}")
            self.logger.debug(f"Headers: {default_headers}")
            self.logger.debug(f"Cookies: {cookies}")
            if data:
                self.logger.debug(f"Request data: {data}")

            # Prepare the request
            req = urllib.request.Request(url, method=method)
            for key, value in default_headers.items():
                req.add_header(key, value)

            # Add cookies
            cookie_string = "; ".join([f"{k}={v}" for k, v in cookies.items()])
            req.add_header("Cookie", cookie_string)

            # Add data if present
            if data:
                json_data = json.dumps(data).encode("utf-8")
                req.data = json_data

            # Make the request
            with urllib.request.urlopen(req) as response:
                self.logger.debug(f"Response status code: {response.status}")
                self.logger.debug(f"Response headers: {response.headers}")

                # Handle gzip encoding
                if response.headers.get("Content-Encoding") == "gzip":
                    content = gzip.decompress(response.read())
                else:
                    content = response.read()

                content_str = content.decode("utf-8")
                self.logger.debug(f"Response content: {content_str[:1000]}...")

                if not content:
                    return None

                return json.loads(content_str)

        except urllib.error.HTTPError as e:
            self.handle_http_error(e)
        except urllib.error.URLError as e:
            self.logger.error(f"URL Error: {str(e)}")
            raise ProviderError(f"API request failed: {str(e)}")
        except json.JSONDecodeError as json_err:
            self.logger.error(f"Failed to parse JSON response: {str(json_err)}")
            self.logger.error(f"Response content: {content_str}")
            raise ProviderError(f"Invalid JSON response from API: {str(json_err)}")

    def handle_http_error(self, e):
        self.logger.debug(f"Request failed: {str(e)}")
        self.logger.debug(f"Response status code: {e.code}")
        self.logger.debug(f"Response headers: {e.headers}")

        try:
            # Check if the content is gzip-encoded
            if e.headers.get("Content-Encoding") == "gzip":
                content = gzip.decompress(e.read())
            else:
                content = e.read()

            # Try to decode the content as UTF-8
            content_str = content.decode("utf-8")
        except UnicodeDecodeError:
            # If UTF-8 decoding fails, try to decode as ISO-8859-1
            content_str = content.decode("iso-8859-1")

        self.logger.debug(f"Response content: {content_str}")

        if e.code == 403:
            error_msg = "Received a 403 Forbidden error."
            raise ProviderError(error_msg)
        elif e.code == 429:
            try:
                error_data = json.loads(content_str)
                resets_at_unix = json.loads(error_data["error"]["message"])["resetsAt"]
                resets_at_local = datetime.fromtimestamp(
                    resets_at_unix, tz=timezone.utc
                ).astimezone()
                formatted_time = resets_at_local.strftime("%a %b %d %Y %H:%M:%S %Z%z")
                error_msg = f"Message limit exceeded. Try again after {formatted_time}"
            except (KeyError, json.JSONDecodeError) as parse_error:
                error_msg = f"HTTP 429: Too Many Requests. Failed to parse error response: {parse_error}"
            self.logger.error(error_msg)
            raise ProviderError(error_msg)
        else:
            error_msg = f"API request failed with status code {e.code}: {content_str}"
            self.logger.error(error_msg)
            raise ProviderError(error_msg)

    def _make_request_stream(self, method, endpoint, data=None):
        url = f"{self.base_url}{endpoint}"
        session_key, _ = self.config.get_session_key("claude.ai")
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "Cookie": f"sessionKey={session_key}",
        }

        req = urllib.request.Request(url, method=method, headers=headers)
        if data:
            req.data = json.dumps(data).encode("utf-8")

        try:
            return urllib.request.urlopen(req)
        except urllib.error.HTTPError as e:
            self.handle_http_error(e)
        except urllib.error.URLError as e:
            raise ProviderError(f"API request failed: {str(e)}")

    def send_message(self, organization_id, chat_id, prompt, timezone="UTC"):
        data = {
            "completion": {
                "model": "claude-2",
                "prompt": prompt,
                "timezone": timezone,
            },
            "conversation_uuid": chat_id,
            "organization_uuid": organization_id,
        }
        endpoint = "/api/append_message"

        response = self._make_request("POST", endpoint, data=data)

        if response.get("error"):
            raise ProviderError(f"Error from Claude.ai: {response['error']}")

        # The response may contain 'completion' with the assistant's reply
        return response.get("completion", "")
