from flask import Flask, render_template, request, jsonify
import requests
from flask_cors import CORS
import logging


app = Flask(__name__)
CORS(app)  # Enable CORS for all routes

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Use HTTP instead of HTTPS unless you have SSL configured
RASA_API_URL = 'http://localhost:5005/webhooks/rest/webhook'


@app.route('/')
def index():
    return render_template('index.html')


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        # Validate incoming request
        if not request.json or 'message' not in request.json:
            logger.error("Invalid request format: %s", request.json)
            return jsonify({
                'response': "Please send your message in the correct format.",
                'status': 'invalid_request'
            }), 400

        user_message = request.json.get('message')
        logger.debug("Received user message: %s", user_message)

        # Prepare payload for Rasa
        payload = {
            "sender": "user_" + str(hash(user_message) % 10000),  # Unique sender ID
            "message": user_message
        }

        headers = {'Content-Type': 'application/json'}
        logger.debug("Sending to Rasa: %s", payload)

        # Send to Rasa with timeout
        rasa_response = requests.post(
            RASA_API_URL,
            json=payload,
            headers=headers,
            timeout=10  # 10 second timeout
        )

        # Check for HTTP errors
        rasa_response.raise_for_status()
        rasa_response_json = rasa_response.json()
        logger.debug("Full Rasa response: %s", rasa_response_json)

        # Handle empty response
        if not rasa_response_json:
            logger.warning("Received empty response from Rasa for message: %s", user_message)
            return jsonify({
                'response': "I'm still learning. Could you try rephrasing that?",
                'status': 'empty_response',
                'original_message': user_message
            })

        # Extract all text responses
        bot_responses = [r.get('text', '').strip() for r in rasa_response_json if r.get('text')]
        bot_response = "\n".join(filter(None, bot_responses))

        # Handle case where responses exist but are empty strings
        if not bot_response:
            logger.warning("Received responses but no text content: %s", rasa_response_json)
            bot_response = "I understand you but don't have a proper response configured yet."

        logger.debug("Sending response to client: %s", bot_response)
        return jsonify({
            'response': bot_response,
            'status': 'success',
            'original_message': user_message,
            'rasa_response': rasa_response_json
        })

    except requests.exceptions.Timeout:
        logger.error("Timeout while connecting to Rasa server")
        return jsonify({
            'response': "I'm taking too long to respond. Please try again shortly.",
            'status': 'timeout_error'
        }), 504

    except requests.exceptions.ConnectionError:
        logger.error("Could not connect to Rasa server at %s", RASA_API_URL)
        return jsonify({
            'response': "I can't connect to my backend service. Is the Rasa server running?",
            'status': 'connection_error',
            'rasa_url': RASA_API_URL
        }), 503

    except requests.exceptions.HTTPError as e:
        logger.error("HTTP error from Rasa: %s - %s", e.response.status_code, e.response.text)
        return jsonify({
            'response': "There was an error processing your request.",
            'status': 'http_error',
            'error_details': str(e)
        }), 502

    except Exception as e:
        logger.exception("Unexpected error processing message: %s", user_message)
        return jsonify({
            'response': "Something unexpected went wrong. Our team has been notified.",
            'status': 'server_error',
            'error': str(e)
        }), 500


if __name__ == '__main__':
    # Print startup information
    logger.info("Starting Flask server...")
    logger.info("Rasa API endpoint: %s", RASA_API_URL)
    logger.info("Debug mode: %s", app.debug)

    app.run(host='0.0.0.0', port=3000, debug=True)