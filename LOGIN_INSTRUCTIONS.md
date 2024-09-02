# Login and Configuration Instructions for Claude OpenAI API Server

This document provides instructions on how to log in and configure the Claude OpenAI API server.

## Running the Server

1. Make sure you have all the required dependencies installed.
2. Run the server using the following command:
   ```
   python claude_openai_api.py
   ```
   If you want to use HTTPS, add the `--use-ssl` flag:
   ```
   python claude_openai_api.py --use-ssl
   ```

## Logging In

The server provides two methods for authentication:

### Method 1: Automatic Login

1. Access the `/login` endpoint using a POST request.
2. The server will attempt to log in to Claude.ai automatically.
3. If successful, it will store the session key for future requests.

### Method 2: Manual Cookie Configuration

1. Open your web browser and navigate to `http://localhost:5000/config` (or `https://localhost:5000/config` if using SSL).
2. You will see a simple form where you can enter a new Claude.ai cookie.
3. To obtain the cookie:
   a. Log in to Claude.ai in your web browser.
   b. Open the browser's developer tools (usually F12 or right-click and select "Inspect").
   c. Go to the "Application" or "Storage" tab.
   d. Under "Cookies", find the cookie for the Claude.ai domain.
   e. Copy the value of the session cookie (usually named something like `sessionKey` or `__Secure-next-auth.session-token`).
4. Paste the copied cookie value into the form on the `/config` page.
5. Click "Update Cookie" to save the new cookie.

## Using the API

After successful login or cookie configuration, you can use the API endpoints:

- `/v1/chat/completions`: For chat completions (POST request)
- `/v1/models`: To list available models (GET request)

Make sure to include the necessary headers and payload as per the OpenAI API specifications.

## Troubleshooting

- If you encounter authentication errors, try updating the cookie using the `/config` page.
- Check the server logs (`claude_openai_api.log`) for any error messages or debugging information.
- Ensure that your Claude.ai account is active and in good standing.

For any further assistance, please refer to the project documentation or contact the support team.