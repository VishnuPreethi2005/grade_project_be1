import requests
from rest_framework.response import Response
import logger

def call_gemini_api(payload):
    try:
        response = requests.post("https://genai.googleapi.com/...", json=payload, headers={
            "Authorization": f"Bearer {os.getenv('GEMINI_API_KEY')}"
        })

        if response.status_code == 401:
            return Response({"error": "Invalid or expired API key"}, status=401)
        elif response.status_code == 403:
            return Response({"error": "Access forbidden. Check API plan."}, status=403)
        elif response.status_code == 429:
            return Response({"error": "Rate limit exceeded"}, status=429)
        elif response.status_code >= 500:
            return Response({"error": "AI service temporarily unavailable"}, status=503)

        return response.json()

    except requests.exceptions.Timeout:
        return Response({"error": "AI request timed out"}, status=503)

    except requests.exceptions.RequestException as e:
        logger.exception("External API request failed")
        return Response({"error": "AI service error. Please try again later."}, status=503)
