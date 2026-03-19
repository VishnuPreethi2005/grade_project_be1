from functools import wraps
from django.utils import timezone
from .models import AnonymousUsage
from django.contrib.auth import get_user_model
from rest_framework.response import Response
from rest_framework import status
import logging
from asgiref.sync import sync_to_async
from decimal import Decimal
from authentication.models import UserCredit, UsageHistory


logger = logging.getLogger(__name__)


def anonymous_rate_limit(view_func):
    """
    Decorator that:
    1. Allows authenticated users unlimited access
    2. Allows anonymous users 3 free hits per 24 hours
    3. Returns 401 when anonymous hits are exhausted
    """

    @wraps(view_func)
    async def _wrapped_view(request, *args, **kwargs):
        User = get_user_model()

        # Check if user is authenticated (either via session or email)
        user = None

        # Standard authentication check
        if hasattr(request, "user") and request.user.is_authenticated:
            user = request.user
        else:
            # Email-based authentication fallback
            user_email = request.query_params.get("email")
            if user_email:
                try:
                    user = await sync_to_async(
                        User.objects.filter(email=user_email).first
                    )()
                    if user:
                        request.user = (
                            user  # Set user on request for downstream use
                        )
                except Exception as e:
                    await sync_to_async(logger.error)(
                        f"Failed to authenticate user by email: {e}"
                    )

        # If authenticated (by any method), bypass rate limiting
        if user is not None:
            return await view_func(request, *args, **kwargs)

        # For anonymous users, apply rate limiting
        ip = get_client_ip(request)
        if not ip or ip == "unknown":
            return Response(
                {
                    "error": "Could not determine your IP address. Authentication required."
                },
                status=status.HTTP_401_UNAUTHORIZED,
            )

        # Get or create usage record
        try:
            usage = await sync_to_async(AnonymousUsage.get_for_ip)(ip)

            if not usage.can_access():
                return Response(
                    {
                        "error": "Daily free limit exhausted. Please authenticate or try again tomorrow.",
                        "hits_remaining": 0,
                        "reset_time": usage.first_hit_time
                        + timezone.timedelta(hours=24),
                    },
                    status=status.HTTP_401_UNAUTHORIZED,
                )

            # Record the hit
            remaining = await sync_to_async(usage.record_hit)()

            # Add headers to inform client about their usage
            response = await view_func(request, *args, **kwargs)
            if isinstance(response, Response):
                response.data["rate_limit"] = {
                    "remaining": remaining,
                    "reset_time": usage.first_hit_time
                    + timezone.timedelta(hours=24),
                }
            return response

        except Exception as e:
            await sync_to_async(logger.error)(
                f"Rate limit error for IP {ip}: {str(e)}"
            )
            # Fail open - allow access if there's an error with rate limiting
            return await view_func(request, *args, **kwargs)

    return _wrapped_view


def get_client_ip(request):
    """
    Get client IP address from request
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0]
    else:
        ip = request.META.get("REMOTE_ADDR", "unknown")
    return ip


def credit_check_decorator(view_func):
    """
    Decorator that:
    1. Checks if authenticated user has sufficient credits (at least 0.003 USD)
    2. Allows the request to proceed if credits are sufficient
    3. Returns 402 Payment Required if credits are insufficient
    4. Deducts the actual cost after API call is complete
    5. Creates UsageHistory record for tracking
    """

    @wraps(view_func)
    async def _wrapped_view(request, *args, **kwargs):
        # Check if user is authenticated
        user = await get_authenticated_user(request)

        if user is None:
            # If not authenticated, pass through to the anonymous_rate_limit
            # decorator
            return await view_func(request, *args, **kwargs)

        # Check if user has sufficient credits
        try:
            # Get user credit
            user_credit = await sync_to_async(
                UserCredit.objects.get_or_create
            )(
                user=user,
                defaults={
                    "free_credit": Decimal("50.00"),
                    "paid_credit": Decimal("0.00"),
                },
            )
            # get_or_create returns a tuple (object, created)
            user_credit = user_credit[0]
            print(f"User credit: {user_credit.total_credit} USD")
            logging.info(f"User credit: {user_credit.total_credit} USD")

            # Check if user has minimum required credit (0.003 USD)
            if user_credit.total_credit < Decimal("0.003"):
                return Response(
                    {
                        "error": "Insufficient credits",
                        "current_balance": float(user_credit.total_credit),
                        "required_minimum": 0.003,
                    },
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )

            # Process the request
            response = await view_func(request, *args, **kwargs)
            print(f"Response in decorators: {response}")
            logging.info(f"Response in decorators: {response}")

            # If there's a cost in the response, deduct it and create usage
            # history
            if isinstance(response, Response) and "cost" in response.data:
                cost = Decimal(str(response.data["cost"]))
                print(f"Cost: {cost} USD")
                logging.info(f"Cost: {cost} USD")

                # Get service type from the view function name or response data
                service_type = response.data.get(
                    "service_type", view_func.__name__
                )

                # Get input length from response data or default to 0
                input_length = response.data.get("input_length", 0)

                # Create usage history record
                await sync_to_async(UsageHistory.objects.create)(
                    user=user,
                    service_type=service_type,
                    input_length=input_length,
                    cost=cost,
                    # reference_id=response.data.get('reference_id')
                )

                # Deduct credits
                await sync_to_async(deduct_user_credit)(user, cost)

                # Update the response with new balance
                updated_credit = await sync_to_async(UserCredit.objects.get)(
                    user=user
                )
                response.data["credits_remaining"] = float(
                    updated_credit.total_credit
                )

            return response

        except Exception as e:
            await sync_to_async(logger.error)(
                f"Credit check error for user {user.id}: {str(e)}"
            )
            # In case of error, allow the request to proceed
            return await view_func(request, *args, **kwargs)

    return _wrapped_view


async def get_authenticated_user(request):
    """Helper function to get authenticated user from request"""
    User = get_user_model()

    # Standard authentication check
    if hasattr(request, "user") and request.user.is_authenticated:
        return request.user

    # Email-based authentication fallback
    user_email = request.query_params.get("email")
    if user_email:
        try:
            user = await sync_to_async(
                User.objects.filter(email=user_email).first
            )()
            if user:
                request.user = user  # Set user on request for downstream use
                return user
        except Exception as e:
            await sync_to_async(logger.error)(
                f"Failed to authenticate user by email: {e}"
            )

    return None


def deduct_user_credit(user, cost):
    """
    Deduct cost from user's credits.
    First from free_credit, then from paid_credit if necessary.
    """
    user_credit = UserCredit.objects.get(user=user)

    # First deduct from free credit
    if user_credit.free_credit >= cost:
        user_credit.free_credit -= cost
    else:
        # If free credit is insufficient, use all free credit and deduct
        # remaining from paid credit
        remaining_cost = cost - user_credit.free_credit
        user_credit.free_credit = Decimal("0.00")
        user_credit.paid_credit -= remaining_cost

    user_credit.save()

    # Log the transaction
    logger.info(
        f"Deducted {cost} USD from user {user.id}. New balance: {user_credit.total_credit} USD"
    )

    return user_credit
