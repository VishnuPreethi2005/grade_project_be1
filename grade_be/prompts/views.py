import logging
from asgiref.sync import sync_to_async
from django.http import HttpResponse
from django.shortcuts import render
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.decorators import parser_classes

from authentication.models import User
from adrf.decorators import api_view

from prompts.models import (
    Translation,
    Transliteration,
    Subscription,
    Entity,
    EmailWriter,
    GeneratedQuestion,
    UserFeedback,
)
from promptRightProd.parameters import input_dict, model_dict
from prompts.src.pipeline import start_point
from utils.email_utils import send_exception_email
from utils.exceptions import (
    AnotherException,
    InputLengthExceededException,
    RetryableException,
    RetryLimitExceededException,
    SomeSpecificException,
)
from prompts.utils import RazorpayOrder
from prompts.serializers import SubscriptionSerializer, UserFeedbackSerializer
import time
from .decorators import anonymous_rate_limit, credit_check_decorator

logger = logging.getLogger(__name__)

# List to store input texts and responses for each translation
translation_history = []
email_history = []
# cost calculation


def cost_cal(input_str: str) -> float:
    # Split the string by '$' and take the part after it
    try:
        dollar_part = input_str.split("$")[-1].strip()
        return float(dollar_part)
    except (IndexError, ValueError):
        raise ValueError("Cost value not found or invalid format.")


async def async_get_prompt(request):
    """
    Asynchronous view function to handle prompt retrieval.
    """
    if request.method == "POST":
        menu = request.POST.get("user_text", "")
        try:
            result = await start_point(menu, model_dict, input_dict)
            return HttpResponse({result})
        except Exception as e:
            logger.exception("An unexpected error occurred: %s", str(e))
            return Response(
                {
                    "error": "An unexpected error occurred. Please try again or contact support."
                },
                status=500,
            )
    else:
        return render(request, "email.html")


def save_translation_sync(request, translation_request, response, cost):
    """
    Synchronous function to save translation in the database.
    """
    user = None

    # Try to get user from request.user
    if hasattr(request, "user") and request.user.is_authenticated:
        user = request.user
    else:
        # Fallback: Try to get user by email
        user_email = (
            request.query_params.get("email")
            if hasattr(request, "query_params")
            else None
        )
        if user_email:
            try:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                user = User.objects.filter(email=user_email).first()
            except Exception as e:
                logger.error(f"Error finding user by email: {e}")

    print(f"User for translation save: {user}")

    return Translation.objects.create(
        user=user,
        input_text=translation_request["text"],
        input_source=translation_request["source"],
        input_destination=translation_request["destination"],
        input_domain=translation_request.get("domain", ""),
        input_subdomain=translation_request.get("subdomain", ""),
        output_response=str(response),
        cost=str(cost),
    )


async def save_translation_async(request, translation_request, response, cost):
    """
    Asynchronous function to save translation in the database.
    """
    return await sync_to_async(save_translation_sync)(
        request, translation_request, response, cost
    )


def save_transliteration_sync(request, translation_request, response, cost):
    """
    Synchronous function to save transliteration in the database.
    """
    user = None

    # Try to get user from request.user
    if hasattr(request, "user") and request.user.is_authenticated:
        user = request.user
    else:
        # Fallback: Try to get user by email
        user_email = (
            request.query_params.get("email")
            if hasattr(request, "query_params")
            else None
        )
        if user_email:
            try:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                user = User.objects.filter(email=user_email).first()
            except Exception as e:
                logger.error(f"Error finding user by email: {e}")
    return Transliteration.objects.create(
        user=user,
        input_text=translation_request["text"],
        input_source=translation_request["source"],
        input_destination=translation_request["destination"],
        output_response=str(response),
        cost=str(cost),
    )


async def save_transliteration_async(
    request, translation_request, response, cost
):
    """
    Asynchronous function to save transliteration in the database.
    """
    return await sync_to_async(save_transliteration_sync)(
        request, translation_request, response, cost
    )


def save_entity_sync(request, entity_request, response, cost):
    user = None

    # Try to get user from request.user
    if hasattr(request, "user") and request.user.is_authenticated:
        user = request.user
    else:
        # Fallback: Try to get user by email
        user_email = (
            request.query_params.get("email")
            if hasattr(request, "query_params")
            else None
        )
        if user_email:
            try:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                user = User.objects.filter(email=user_email).first()
            except Exception as e:
                logger.error(f"Error finding user by email: {e}")
    return Entity.objects.create(
        user=user,
        input_text=entity_request["text"],
        entity=entity_request["Entity"],
        custom_entity=entity_request["CustomEntity"],
        output_response=str(response),
        cost=str(cost),
    )


async def save_entity_async(request, entity_request, response, cost):
    return await sync_to_async(save_entity_sync)(
        request, entity_request, response, cost
    )


def save_counts_of_user(request):
    if isinstance(request.user, User):
        user = User.objects.get(email=request.user.email)
        if user.free_trial_hits < 1000:
            user.free_trial_hits += 1
            user.save()
        else:
            return False


async def save_count_async(request):
    return await sync_to_async(save_counts_of_user)(request)


@api_view(["GET"])
@credit_check_decorator
@anonymous_rate_limit
async def get_translation(request, *args, **kwargs):
    """
    Asynchronous view function to handle translation requests.
    """
    print("[TRANSLATION VIEW] Processing translation request")
    user_email = request.query_params.get("email")
    if not user_email:
        return Response(
            {"error": "Authentication required. Email is missing."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    global translation_history

    if request.method == "GET":
        try:
            res = await save_count_async(request)
            if not res:
                return Response(
                    {"translation": "Dear user kindly subscribe"},
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
        except Exception:
            pass

        try:
            menu = "translate"
            max_length_limit = 1000
            input_text = request.query_params.get("inputText", "")

            if not input_text:
                return Response(
                    {"error": "Input text is required"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if len(input_text) > max_length_limit:
                return Response(
                    {
                        "error": f"Input text exceeds the maximum length limit of {max_length_limit} characters."
                    },
                    status=400,
                )

            translation_request = {
                "text": input_text,
                "source": request.query_params.get(
                    "sourceLanguage", "English"
                ),
                "destination": request.query_params.get(
                    "destinationLanguage", ""
                ),
                "domain": request.query_params.get("domain", ""),
                "subdomain": request.query_params.get("subDomain", ""),
            }
            model_dict = {
                "model": request.query_params.get("model", "gpt-3.5-turbo"),
                "temperature": float(
                    request.query_params.get("temperature", 0.7)
                ),
                "max_tokens": int(request.query_params.get("maxOutput", 1000)),
                "top_k": int(request.query_params.get("TopK", 1)),
            }

            response, cost = await start_point(
                menu, model_dict, translation_request
            )
            await save_translation_async(
                request, translation_request, response, cost
            )
            translation_history.append(
                {
                    "input": input_text,
                    "response": response,
                    "timestamp": time.time(),
                }
            )

            return Response(
                {
                    "translation": response,
                    "cost": cost_cal(str(cost)),
                    "service_type": "translation",
                    "input_length": len(input_text),
                }
            )

        except SomeSpecificException:
            logger.exception("A specific error occurred during translation.")
            return Response(
                {"error": "A specific error occurred during translation."},
                status=500,
            )

        except AnotherException:
            logger.exception("Another error occurred during translation.")
            return Response(
                {"error": "Another error occurred during translation."},
                status=500,
            )

        except RetryableException as e:
            logger.warning(
                "A retryable error occurred: %s. Retrying...", str(e)
            )
            retry_count = 0
            while retry_count < 3:
                try:
                    response, cost = await start_point(
                        menu, model_dict, translation_request
                    )
                    await save_translation_async(
                        request, translation_request, response, cost
                    )
                    return Response(
                        {
                            "translation": response,
                            "cost": cost_cal(str(cost)),
                            "service_type": "translation",
                            "input_length": len(input_text),
                        }
                    )
                except RetryableException as e:
                    retry_count += 1
                    logger.warning("Retry %d failed: %s", retry_count, str(e))
                    continue

            logger.error("Max retries exceeded for translation.")
            raise RetryLimitExceededException(
                "Max retries exceeded for translation."
            )

        except InputLengthExceededException:
            logger.exception("Input text length exceeded the limit.")
            return Response(
                {"error": "Input text length exceeded the limit."}, status=400
            )

        except Exception as e:
            logger.exception("An unexpected error occurred: %s", str(e))
            send_exception_email("Exception Occurred", str(e))
            return Response(
                {
                    "error": "An unexpected error occurred. Please try again or contact support."
                },
                status=500,
            )


def save_email_sync(request, email_request, response, cost):
    """
    Synchronous function to save email in the database.
    """
    user = None

    # Try to get user from request.user
    if hasattr(request, "user") and request.user.is_authenticated:
        user = request.user
    else:
        # Fallback: Try to get user by email
        user_email = (
            request.query_params.get("email")
            if hasattr(request, "query_params")
            else None
        )
        if user_email:
            try:
                from django.contrib.auth import get_user_model

                User = get_user_model()
                user = User.objects.filter(email=user_email).first()
            except Exception as e:
                logger.error(f"Error finding user by email: {e}")
    return EmailWriter.objects.create(
        user=user,
        selectedType=email_request["type_of_mail"],
        tone=email_request["tone"],
        recipient=email_request["recipient"],
        purpose=email_request["purpose"],
        personalized=email_request["content"],
        generated_email=str(response),
        cost=str(cost),
    )


async def save_email_async(request, email_request, response, cost):
    """
    Asynchronous function to save email in the database.
    """
    return await sync_to_async(save_email_sync)(
        request, email_request, response, cost
    )


@api_view(["GET"])
@credit_check_decorator
@anonymous_rate_limit
async def get_email(request, *args, **kwargs):
    """
    Asynchronous view function to handle email writing requests.
    """
    print("[TRANSLATION VIEW] Processing email writer request")
    user_email = request.query_params.get("email")
    if not user_email:
        return Response(
            {"error": "Authentication required. Email is missing."},
            status=status.HTTP_401_UNAUTHORIZED,
        )
    global email_history

    if request.method == "GET":
        try:
            res = await save_count_async(request)
            if not res:
                return Response(
                    {"email": "Dear user kindly subscribe"},
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
        except Exception:
            pass

        try:
            menu = "write_email"

            max_length_limit = 1000
            input_text = request.query_params.get("personalized", "")

            if len(input_text) > max_length_limit:
                return Response(
                    {
                        "error": "Input text exceeds the maximum length limit of {} characters.".format(
                            max_length_limit
                        )
                    },
                    status=400,
                )

            email_request = {
                "type_of_mail": request.query_params.get("selectedType", ""),
                "tone": request.query_params.get("tone", ""),
                "recipient": request.query_params.get("recipient", ""),
                "purpose": request.query_params.get("purpose", ""),
                "content": input_text,
            }
            model_dict = {
                "model": request.query_params.get("model", ""),
                "temperature": request.query_params.get("temperature", ""),
                "max_tokens": request.query_params.get("maxOutput", ""),
                "top_k": request.query_params.get("TopK", ""),
            }
            print(email_request)

            response, cost = await start_point(menu, model_dict, email_request)

            email_history.append({"input": input_text, "response": response})

            await save_email_async(request, email_request, response, cost)

            return Response(
                {
                    "email": response,
                    "cost": cost_cal(str(cost)),
                    "service_type": "emailwriter",
                    "input_length": len(input_text),
                }
            )

        except SomeSpecificException:
            logger.exception(
                "A specific error occurred during email composition."
            )
            return Response(
                {
                    "error": "A specific error occurred during email composition."
                },
                status=500,
            )

        except AnotherException:
            logger.exception(
                "Another error occurred during email composition."
            )
            return Response(
                {"error": "Another error occurred during email composition."},
                status=500,
            )

        except RetryableException as e:
            logger.warning(
                "A retryable error occurred: %s. Retrying...", str(e)
            )
            retry_count = 0
            while retry_count < 3:
                try:
                    response, cost = await start_point(
                        menu, model_dict, email_request
                    )
                    await save_email_async(
                        request, email_request, response, cost
                    )
                    return Response(
                        {
                            "email": response,
                            "cost": cost_cal(str(cost)),
                            "service_type": "emailwriter",
                            "input_length": len(input_text),
                        }
                    )
                except RetryableException as e:
                    retry_count += 1
                    logger.warning("Retry %d failed: %s", retry_count, str(e))
                    continue

            logger.error("Max retries exceeded for email composition.")
            raise RetryLimitExceededException(
                "Max retries exceeded for email composition."
            )

        except InputLengthExceededException:
            logger.exception("Input text length exceeded the limit.")
            return Response(
                {"error": "Input text length exceeded the limit."}, status=400
            )

        except Exception as e:
            logger.exception("An unexpected error occurred: %s", str(e))
            send_exception_email("Exception Occurred", str(e))
            return Response(
                {
                    "error": "An unexpected error occurred. Please try again or contact support."
                },
                status=500,
            )


@api_view(["GET"])
@credit_check_decorator
@anonymous_rate_limit
async def get_transliteration(request, *args, **kwargs):
    """
    Asynchronous view function to handle transliteration requests.
    """
    if request.method == "GET":
        try:
            res = await save_count_async(request)
            if not res:
                return Response(
                    {"transliteration": "Dear user kindly subscribe"},
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
        except Exception:
            pass

        try:
            menu = "transliterate"

            max_length_limit = 1000
            input_text = request.query_params.get("inputText", "")

            if len(input_text) > max_length_limit:
                return Response(
                    {
                        "error": "Input text exceeds the maximum length limit of {} characters.".format(
                            max_length_limit
                        )
                    },
                    status=400,
                )

            translation_request = {
                "text": input_text,
                "source": request.query_params.get("sourceLanguage", ""),
                "destination": request.query_params.get(
                    "destinationLanguage", ""
                ),
            }
            model_dict = {
                "model": request.query_params.get("model", ""),
                "temperature": request.query_params.get("temperature", ""),
                "max_tokens": request.query_params.get("maxOutput", ""),
                "top_k": request.query_params.get("TopK", ""),
            }

            response, cost = await start_point(
                menu, model_dict, translation_request
            )

            await save_transliteration_async(
                request, translation_request, response, cost
            )
            print(response)

            return Response(
                {
                    "transliteration": response,
                    "cost": cost_cal(str(cost)),
                    "service_type": "transliteration",
                    "input_length": len(input_text),
                }
            )

        except SomeSpecificException:
            logger.exception(
                "A specific error occurred during transliteration."
            )
            return Response(
                {"error": "A specific error occurred during transliteration."},
                status=500,
            )

        except AnotherException:
            logger.exception("Another error occurred during transliteration.")
            return Response(
                {"error": "Another error occurred during transliteration."},
                status=500,
            )

        except RetryableException as e:
            logger.warning(
                "A retryable error occurred: %s. Retrying...", str(e)
            )
            retry_count = 0
            while retry_count < 3:
                try:
                    response, cost = await start_point(
                        menu, model_dict, translation_request
                    )
                    await save_transliteration_async(
                        request, translation_request, response, cost
                    )
                    return Response(
                        {
                            "transliteration": response,
                            "cost": cost_cal(str(cost)),
                            "service_type": "transliteration",
                            "input_length": len(input_text),
                        }
                    )
                except RetryableException as e:
                    retry_count += 1
                    logger.warning("Retry %d failed: %s", retry_count, str(e))
                    continue

            logger.error("Max retries exceeded for transliteration.")
            raise RetryLimitExceededException(
                "Max retries exceeded for transliteration."
            )

        except InputLengthExceededException:
            logger.exception("Input text length exceeded the limit.")
            return Response(
                {"error": "Input text length exceeded the limit."}, status=400
            )

        except Exception as e:
            logger.exception("An unexpected error occurred: %s", str(e))
            send_exception_email("Exception Occurred", str(e))
            return Response(
                {
                    "error": "An unexpected error occurred. Please try again or contact support."
                },
                status=500,
            )


@api_view(["GET"])
@credit_check_decorator
@anonymous_rate_limit
async def get_entity(request, *args, **kwargs):
    if request.method == "GET":
        try:
            res = await save_count_async(request)
            if not res:
                return Response(
                    {"entity": "Dear user kindly subscribe"},
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
        except Exception:
            pass

        try:
            menu = "entity"
            max_length_limit = 1000
            input_text = request.query_params.get("input", "")

            if len(input_text) > max_length_limit:
                return Response(
                    {
                        "error": f"Input text exceeds the maximum length limit of {max_length_limit} characters."
                    },
                    status=400,
                )

            entity_request = {
                "text": input_text,
                "Entity": request.query_params.get("entities", ""),
                "CustomEntity": request.query_params.get("customEntity", ""),
            }
            model_dict = {
                "model": request.query_params.get("model", ""),
                "temperature": request.query_params.get("temperature", ""),
                "max_tokens": request.query_params.get("maxOutput", ""),
                "top_k": request.query_params.get("TopK", ""),
            }

            response, cost = await start_point(
                menu, model_dict, entity_request
            )
            await save_entity_async(request, entity_request, response, cost)
            print(f"{response} this is ....")

            return Response(
                {
                    "entity": response,
                    "cost": cost_cal(str(cost)),
                    "service_type": "entity",
                    "input_length": len(input_text),
                }
            )

        except SomeSpecificException:
            logger.exception(
                "A specific error occurred during entity extraction."
            )
            return Response(
                {
                    "error": "A specific error occurred during entity extraction."
                },
                status=500,
            )

        except AnotherException:
            logger.exception(
                "Another error occurred during entity extraction."
            )
            return Response(
                {"error": "Another error occurred during entity extraction."},
                status=500,
            )

        except RetryLimitExceededException as e:
            logger.exception(
                "Retry limit exceeded for entity extraction request: %s",
                str(e),
            )
            return Response(
                {
                    "error": "Retry limit exceeded for entity extraction request."
                },
                status=500,
            )

        except RetryableException as e:
            logger.exception(
                "Retryable error occurred during entity extraction request: %s",
                str(e),
            )
            return Response(
                {
                    "error": "Retryable error occurred during entity extraction request."
                },
                status=500,
            )

        except InputLengthExceededException as e:
            logger.exception(
                "Input length exceeded during entity extraction request: %s",
                str(e),
            )
            return Response(
                {
                    "error": "Input length exceeded during entity extraction request."
                },
                status=400,
            )

        except Exception as e:
            logger.exception("An unexpected error occurred: %s", str(e))
            send_exception_email("Exception Occurred", str(e))
            return Response(
                {
                    "error": "An unexpected error occurred. Please try again or contact support."
                },
                status=500,
            )


class SubscriptionViewset(APIView):
    permission_classes = [IsAuthenticated]
    queryset = Subscription.objects.all()

    def post(self, request):
        razorpay = RazorpayOrder()

        user = request.user
        try:
            data = request.data
            amount = data["amount"]

        except Exception:
            return Response(
                {"message": "amount is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create the order
        try:
            orderCreate = razorpay.create_order(amount)
        except Exception:
            return Response(
                {"message": "key is not set"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            subscription = Subscription.objects.create(
                user=user, amount=amount, orderID=orderCreate["id"]
            )
            subscriptionSerializer = SubscriptionSerializer(subscription)
        except Exception:
            return Response(
                {"message": "Object is not created in subscription table"},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        return Response(
            {
                "message": "success",
                "subscription": subscriptionSerializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


@api_view(["GET"])
@credit_check_decorator
@anonymous_rate_limit
async def get_question(request, *args, **kwargs):
    """
    Asynchronous view function to handle question generation requests.
    """
    global question_request
    if request.method == "GET":
        try:
            # Check and save user hit counts
            res = await save_count_async(request)
            if not res:
                return Response(
                    {"question": "Dear user kindly subscribe"},
                    status=status.HTTP_402_PAYMENT_REQUIRED,
                )
        except Exception:
            pass

        try:
            # Maximum input text length limit
            max_length_limit = 1000

            # Retrieve query parameters
            question_type = request.query_params.get("questionType", "")
            num_questions = request.query_params.get("numQuestionsValue", "")
            bloom = request.query_params.get("bloomValue", "")
            level = request.query_params.get("levelValue", "")
            num_options = request.query_params.get("numberOfOptionsValue", "")
            option_type = request.query_params.get("optionTypeValue", "")
            num_missing_words = request.query_params.get(
                "numberOfMissingWordsValue", ""
            )
            representing_words = request.query_params.get(
                "representingWordsValue", ""
            )
            num_items = request.query_params.get("numberOfItemsValue", "")
            learning_obj = request.query_params.get("learningObj", "")
            provide_answer = request.query_params.get("provideAnswerValue", "")
            explanation = request.query_params.get("explanationValue", "")
            format_value = request.query_params.get("formatValue", "")
            text = request.query_params.get("enterTheText", "")
            similar_question = request.query_params.get("similarQuestion", "")
            topicValue = request.query_params.get("topicValue", "")
            subtopicValue = request.query_params.get("subtopicValue", "")
            exampleValue = request.query_params.get("exampleValue", "")
            conceptValue = request.query_params.get("conceptValue", "")
            constraintsValue = request.query_params.get("constraintsValue", "")
            keywordsValue = request.query_params.get("keywordsValue", "")
            showTopic = request.query_params.get("showTopic", "")
            showContent = request.query_params.get("showContent", "")
            showSimilar = request.query_params.get("showSimilar", "")

            # Construct the question request
            question_request = {
                "questionType": question_type,
                "numQuestionsValue": num_questions,
                "bloomValue": bloom,
                "levelValue": level,
                "numberOfOptionsValue": num_options,
                "optionTypeValue": option_type,
                "numberOfMissingWordsValue": num_missing_words,
                "representingWordsValue": representing_words,
                "numberOfItemsValue": num_items,
                "learningObj": learning_obj,
                "provideAnswerValue": provide_answer,
                "explanationValue": explanation,
                "formatValue": format_value,
            }

            model_dict = {
                "model": "gpt-4o-mini",
                "temperature": 1,
                "max_tokens": 2000,
                "top_k": 1,
            }

            # Generate question using the pipeline
            if showContent == "true":
                question_request["text"] = text
                respons, cost = await start_point(
                    "enter_text", model_dict, question_request
                )
                service_type = "question_content"
            elif showSimilar == "true":
                question_request["similar_question"] = similar_question
                respons, cost = await start_point(
                    "similarQuestion", model_dict, question_request
                )
                service_type = "question_similar"
            elif showTopic == "true":
                question_request["topicValue"] = topicValue
                question_request["subtopicValue"] = subtopicValue
                question_request["exampleValue"] = exampleValue
                question_request["conceptValue"] = conceptValue
                question_request["constraintsValue"] = constraintsValue
                question_request["keywordsValue"] = keywordsValue
                respons, cost = await start_point(
                    "topic", model_dict, question_request
                )
                service_type = "question_topic"

            # Calculate input length based on the type of question generation
            input_length = 0
            if showContent == "true":
                input_length = len(text)
            elif showSimilar == "true":
                input_length = len(similar_question)
            elif showTopic == "true":
                input_length = len(str(question_request))

            # Save the generated question in the database
            await save_question_async(request, question_request, respons, cost)

            return Response(
                {
                    "question": respons,
                    "cost": cost_cal(str(cost)),
                    "service_type": service_type,
                    "input_length": input_length,
                }
            )

        except SomeSpecificException:
            logger.exception(
                "A specific error occurred during question generation."
            )
            return Response(
                {
                    "error": "A specific error occurred during question generation."
                },
                status=500,
            )

        except AnotherException:
            logger.exception(
                "Another error occurred during question generation."
            )
            return Response(
                {
                    "error": "Another error occurred during question generation."
                },
                status=500,
            )

        except RetryableException as e:
            logger.warning(
                "A retryable error occurred: %s. Retrying...", str(e)
            )
            retry_count = 0
            while retry_count < 3:
                try:
                    response, cost = await start_point(
                        "generateQuestion", model_dict, question_request
                    )
                    await save_translation_async(
                        request, question_request, response, cost
                    )
                    return Response(
                        {
                            "question": response,
                            "cost": cost_cal(str(cost)),
                            "service_type": service_type,
                            "input_length": input_length,
                        }
                    )
                except RetryableException as e:
                    retry_count += 1
                    logger.warning("Retry %d failed: %s", retry_count, str(e))
                    continue

            logger.error("Max retries exceeded for question generation.")
            raise RetryLimitExceededException(
                "Max retries exceeded for question generation."
            )

        except InputLengthExceededException:
            logger.exception("Input text length exceeded the limit.")
            return Response(
                {
                    "error": f"Input text length exceeded the limit of {max_length_limit} characters."
                },
                status=400,
            )

        except Exception as e:
            logger.exception("An unexpected error occurred: %s", str(e))
            send_exception_email("Exception Occurred", str(e))
            return Response(
                {
                    "error": "An unexpected error occurred. Please try again or contact support."
                },
                status=500,
            )


async def save_question_async(request, question_request, response, cost):
    return await sync_to_async(save_question_sync)(
        request, question_request, response, cost
    )


def save_question_sync(request, question_request, response, cost):
    """
    Synchronous function to save generated questions in the database.
    """
    def truncate(value, max_length=100):
        """Truncate string value to max_length if it's longer."""
        if value is None:
            return None
        str_value = str(value)
        return str_value[:max_length] if len(str_value) > max_length else str_value
    
    user = request.user if isinstance(request.user, User) else None
    return GeneratedQuestion.objects.create(
        user=user,
        question_type=truncate(question_request.get("questionType")),
        num_questions=truncate(question_request.get("numQuestionsValue")),
        bloom=truncate(question_request.get("bloomValue")),
        level=truncate(question_request.get("levelValue")),
        num_options=truncate(question_request.get("numberOfOptionsValue")),
        option_type=truncate(question_request.get("optionTypeValue")),
        num_missing_words=truncate(question_request.get("numberOfMissingWordsValue")),
        representing_words=truncate(question_request.get("representingWordsValue")),
        num_items=truncate(question_request.get("numberOfItemsValue")),
        learning_obj=truncate(question_request.get("learningObj")),
        provide_answer=truncate(question_request.get("provideAnswerValue")),
        explanation=truncate(question_request.get("explanationValue")),
        format_value=truncate(question_request.get("formatValue")),
        response=str(response),
        cost=truncate(str(cost)),
    )


@api_view(["POST"])
def submit_feedback(request):
    """
    Handle user feedback submission from the frontend
    """
    print("=== Feedback submission received ===")
    print("Request method:", request.method)
    print("Request data:", request.data)
    print("Request user:", request.user)
    print(
        "Request META:",
        {k: v for k, v in request.META.items() if k.startswith("HTTP_")},
    )

    try:
        serializer = UserFeedbackSerializer(data=request.data)
        print("Serializer data:", request.data)
        print("Serializer is valid:", serializer.is_valid())

        if serializer.is_valid():
            print("Serializer errors:", serializer.errors)

            # Get user from request if authenticated
            user = None
            if hasattr(request, "user") and request.user.is_authenticated:
                user = request.user
                print("User authenticated:", user.email)
            else:
                print("User not authenticated")

                # Try to get user from Authorization header (JWT token)
                auth_header = request.META.get("HTTP_AUTHORIZATION", "")
                if auth_header.startswith("Bearer "):
                    token = auth_header.split(" ")[1]
                    print("JWT token found:", token[:20] + "...")

                    try:
                        from rest_framework_simplejwt.tokens import AccessToken
                        from django.contrib.auth import get_user_model

                        User = get_user_model()

                        # Decode the token
                        access_token = AccessToken(token)
                        user_id = access_token["user_id"]
                        user = User.objects.get(id=user_id)
                        print("User found from JWT:", user.email)
                    except Exception as e:
                        print("Error decoding JWT token:", str(e))
                        user = None
            print("User for feedback:", user)

            # Get IP address
            ip_address = None
            if hasattr(request, "META"):
                x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
                if x_forwarded_for:
                    ip_address = x_forwarded_for.split(",")[0].strip()
                else:
                    ip_address = request.META.get("REMOTE_ADDR")
            print("IP address:", ip_address)

            # Create feedback object
            feedback = UserFeedback.objects.create(
                user=user,
                emoji_rating=serializer.validated_data.get("emoji_rating"),
                comment=serializer.validated_data.get("comment"),
                ip_address=ip_address,
            )

            print("Feedback created successfully:", feedback.id)

            return Response(
                {
                    "message": "Feedback submitted successfully",
                    "feedback_id": feedback.id,
                },
                status=status.HTTP_201_CREATED,
            )
        else:
            print("Serializer validation failed:", serializer.errors)
            return Response(
                serializer.errors, status=status.HTTP_400_BAD_REQUEST
            )

    except Exception as e:
        print("Exception in submit_feedback:", str(e))
        logger.exception("Error submitting feedback: %s", str(e))
        return Response(
            {"error": "An error occurred while submitting feedback"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )


@api_view(["GET"])
def get_feedback_list(request):
    """
    Get all feedback for admin dashboard
    """
    try:
        # Check if user is admin
        if (
            not hasattr(request, "user")
            or not request.user.is_authenticated
            or not request.user.is_admin
        ):
            return Response(
                {"error": "Admin access required"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # Get all feedback with user information
        feedback_list = UserFeedback.objects.select_related("user").order_by(
            "-created"
        )

        feedback_data = []
        for feedback in feedback_list:
            feedback_data.append(
                {
                    "id": feedback.id,
                    "user_email": (
                        feedback.user.email if feedback.user else "Anonymous"
                    ),
                    "user_name": (
                        feedback.user.username
                        if feedback.user
                        else "Anonymous"
                    ),
                    "emoji_rating": feedback.emoji_rating,
                    "comment": feedback.comment,
                    "ip_address": feedback.ip_address,
                    "created": feedback.created.strftime("%Y-%m-%d %H:%M:%S"),
                    "modified": feedback.modified.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                }
            )

        return Response(
            {"data": feedback_data, "count": len(feedback_data)},
            status=status.HTTP_200_OK,
        )

    except Exception as e:
        logger.exception("Error fetching feedback list: %s", str(e))
        return Response(
            {"error": "An error occurred while fetching feedback"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
async def query_with_pdf(request):
    """
    Accepts a PDF or DOCX file, reads its content, and generates questions.
    """
    try:
        file = request.FILES.get("file")
        if not file:
            return Response({"error": "No file uploaded."}, status=400)

        content = ""
        try:
            if file.name.lower().endswith(".pdf"):
                import PyPDF2
                pdf_reader = PyPDF2.PdfReader(file)
                content = " ".join([page.extract_text() for page in pdf_reader.pages if page.extract_text()])
            elif file.name.lower().endswith(".docx"):
                from docx import Document
                doc = Document(file)
                content = "\n".join([para.text for para in doc.paragraphs])
            else:
                return Response({"error": "Unsupported file type."}, status=400)
        except Exception as e:
            logger.exception("Failed to read file: %s", str(e))
            return Response({"error": f"Failed to read file: {str(e)}"}, status=500)

        if not content or len(content.strip()) == 0:
            return Response({"error": "The uploaded file appears to be empty or could not be read."}, status=400)

        model_dict = {
            "model": "gpt-4o-mini",
            "temperature": 1,
            "max_tokens": 2000,
            "top_k": 1,
        }
        # Get questionType from either questionType or qp_pat field
        question_type = request.data.get("questionType") or request.data.get("qp_pat", "")
        # Get numQuestionsValue, defaulting to 1 if not provided
        num_questions = request.data.get("num_questions") or request.data.get("numQuestionsValue", "1")
        
        question_request = {
            "text": content,
            "subject": request.data.get("subject", ""),
            "qp_pat": request.data.get("qp_pat", ""),
            "topics": request.data.get("topics", ""),
            "filename": request.data.get("filename", ""),
            "questionType": question_type,
            "numQuestionsValue": num_questions,
            "bloomValue": request.data.get("bloom_level", request.data.get("bloomValue", "")),
            "levelValue": request.data.get("difficulty", request.data.get("levelValue", "")),
            "learningObj": request.data.get("learning_obj", request.data.get("learningObj", "")),
            "numberOfOptionsValue": request.data.get("num_options", request.data.get("numberOfOptionsValue", "")),
            "optionTypeValue": request.data.get("option_type", request.data.get("optionTypeValue", "")),
            "numberOfMissingWordsValue": request.data.get("num_missing_words", request.data.get("numberOfMissingWordsValue", "")),
            "representingWordsValue": request.data.get("missing_word_style", request.data.get("representingWordsValue", "")),
            "numberOfItemsValue": request.data.get("num_items", request.data.get("numberOfItemsValue", "")),
            "provideAnswerValue": request.data.get("provide_answer", request.data.get("provideAnswerValue", "")),
            "explanationValue": request.data.get("explanation", request.data.get("explanationValue", "")),
            "formatValue": request.data.get("output_format", request.data.get("formatValue", "")),
        }
        try:
            questions, cost = await start_point("enter_text", model_dict, question_request)
            try:
                calculated_cost = cost_cal(str(cost))
            except Exception as cost_error:
                logger.warning("Failed to calculate cost: %s. Using cost value as-is.", str(cost_error))
                calculated_cost = float(cost) if isinstance(cost, (int, float)) else 0.0
            
            return Response({
                "questions": questions,
                "cost": calculated_cost,
                "input_length": len(content),
            })
        except Exception as e:
            logger.exception("An unexpected error occurred in query_with_pdf: %s", str(e))
            send_exception_email("Exception in query_with_pdf", str(e))
            return Response({
                "error": "An unexpected error occurred. Please try again or contact support."
            }, status=500)
    except Exception as e:
        logger.exception("An unexpected error occurred in query_with_pdf: %s", str(e))
        send_exception_email("Exception in query_with_pdf", str(e))
        return Response({
            "error": "An unexpected error occurred. Please try again or contact support."
        }, status=500)
