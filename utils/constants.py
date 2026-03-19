ADMIN_EMAILS = [
    "abigogreen@gmail.com",
    # Add other admin emails here
]


def is_admin_email(email):
    """
    Check if the given email is in the admin list
    """
    return email in ADMIN_EMAILS
