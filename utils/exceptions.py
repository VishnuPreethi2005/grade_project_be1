# utils/exceptions.py


"""
Custom exceptions for handling various scenarios.

This module defines custom exception classes for handling specific scenarios in the application.

Classes:
    SomeSpecificException:
        Custom exception for a specific scenario.
    AnotherException:
        Another custom exception.
    InputLengthExceededException:
        Custom exception for input text exceeding the maximum length limit.
    RetryableException:
        Custom exception for retryable errors during asynchronous processing.
    RetryLimitExceededException:
        Custom exception for exceeding the maximum number of retries.
    UnexpectedException:
        Generic exception for unexpected errors.

Notes:
    Each exception class provides a brief description of the scenario it represents.
    These exceptions can be raised in the application code to handle different error conditions.

Example:
    try:
        # Code that may raise an exception
        if error_condition:
            raise SomeSpecificException("Error message")
    except SomeSpecificException as e:
        # Handle the exception
        print("An error occurred:", str(e))
"""


class SomeSpecificException(Exception):
    """Custom exception for a specific scenario."""


class AnotherException(Exception):
    """Another custom exception."""


class InputLengthExceededException(Exception):
    """Custom exception for input text exceeding the maximum length limit."""


class RetryableException(Exception):
    """Custom exception for retryable errors during asynchronous processing."""


class RetryLimitExceededException(Exception):
    """Custom exception for exceeding the maximum number of retries."""


class UnexpectedException(Exception):
    pass
