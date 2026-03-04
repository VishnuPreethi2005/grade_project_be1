# utils/email_utils.py

"""
Send an email notification for an exception.

This function sends an email notification to the designated recipient(s) when an exception occurs.

Parameters:
    subject (str): The subject of the email.
    message (str): The body of the email.

Returns:
    None

Email Configuration:
    The function uses settings.EMAIL_HOST_USER as the sender's email address.
    The recipient_list should contain the email address(es) of the recipient(s) who will receive the notification.
    Ensure that Django's email settings are properly configured in settings.py.

Example:
    send_exception_email("Error Occurred", "An error occurred in the application.")
"""


from django.core.mail import send_mail
from django.conf import settings


def send_exception_email(subject, message):

    from_email = settings.EMAIL_HOST_USER
    recipient_list = ["mail.send@gmail.com"]  # app owner's or company's email
    send_mail(subject, message, from_email, recipient_list)
