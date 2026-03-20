# utils/middleware.py
from django.http import JsonResponse
from utils.exceptions import (
    SomeSpecificException,
    AnotherException,
    RetryableException,
    RetryLimitExceededException,
    UnexpectedException,
)
from django.core.mail import mail_admins


"""
Custom exception handling middleware for Django.

This module defines a custom middleware class for handling exceptions in Django applications.

Classes:
    MyExceptionHandlerMiddleware:
        Middleware class for handling exceptions.
        It catches different types of exceptions and provides appropriate responses.

Notes:
    - The middleware catches specific exceptions and returns corresponding JSON responses with error messages.
    - If an unexpected exception occurs, an email is sent to the app owners notifying them of the error.
    - The middleware ensures that the application responds with informative error messages for different scenarios.

Example:
    To use this middleware, include it in the MIDDLEWARE setting in Django's settings.py file:
    ```
    MIDDLEWARE = [
        ...
        'utils.middleware.MyExceptionHandlerMiddleware',
        ...
    ]
    ```
"""


class MyExceptionHandlerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)

        except UnexpectedException as e:
            # Send an email to app owners
            mail_admins(
                "Unexpected Exception Occurred",
                f"The following unexpected exception occurred:\n\n{str(e)}",
                fail_silently=False,
            )
            response = JsonResponse(
                {"error": "An unexpected error occurred."}, status=500
            )

        except SomeSpecificException as e:
            response = JsonResponse(
                {"error": "Some specific error occurred."}, status=400
            )

        except AnotherException as e:
            response = JsonResponse(
                {"error": "Another error occurred."}, status=400
            )

        except RetryableException as e:
            response = JsonResponse(
                {"error": "A retryable error occurred. Retrying..."},
                status=500,
            )

        except RetryLimitExceededException as e:
            response = JsonResponse(
                {"error": "Maximum retries reached. Failed to process."},
                status=500,
            )

        except Exception as e:
            response = JsonResponse(
                {
                    "error": "An unexpected error occurred. Please try again or contact support."
                },
                status=500,
            )

        return response
