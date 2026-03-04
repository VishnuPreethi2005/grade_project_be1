import logging
from rest_framework.decorators import api_view,throttle_classes
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.views import APIView
import json
from rest_framework import status, serializers
import re
from rest_framework.decorators import api_view


from executor.utils.auth import require_api_key
import traceback
from executor.throttles import CodeRunRateThrottle 



from .models import Question
from .serializers import QuestionSerializer
from .run_code import run_code_logic

from .question_generator import generate_questions_logic
from .code_grader import generate_grading_json  # Or grade_code_logic if renamed

logger = logging.getLogger(__name__)


# ---- ViewSet for Question with filtering, searching, ordering ----
class QuestionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing coding questions.

    Provides CRUD operations along with filtering, searching, and ordering support.

    Features:
    - Filter by difficulty, topic, company, or custom_id
    - Search by title, topic name, company name, difficulty, or custom_id
    - Supports ordering by any model field (optional via query param)

    Example:
        GET /api/questions/?search=linkedlist&difficulty=Easy
    """
    queryset = Question.objects.all()
    serializer_class = QuestionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['difficulty', 'topics', 'companies', 'custom_id']
    search_fields = ['title', 'topics__name', 'companies__name', 'difficulty', 'custom_id']


# ---- API Endpoints ----

@api_view(['POST'])
def generate_questions(request: Request) -> Response:
    """
    POST API endpoint to generate coding questions using an AI model.

    Expects a JSON body with:
    {
        "topic": "string",
        "difficulty": "Easy" | "Medium" | "Hard"
    }

    Returns:
        Response: A list of newly generated questions or error details.
    """
    logger.info("Received POST request to generate questions.")
    return generate_questions_logic(request)




from .code_grader import generate_grading_json  # Make sure this is updated to take public testcases

@api_view(['POST'])
def grade_code(request):
    """
    Grade a user's code using AI-generated rubric based on public test cases.
    """

    logger.info("Received POST request to grade code.")

    try:
        code = request.data.get('code')
        question = request.data.get('question')
        results = request.data.get('results', [])

        logger.info(f"Received data: code={bool(code)}, question={bool(question)}, results={bool(results)}")
        logger.debug(f"Raw request data: {json.dumps(request.data, indent=2)}")

        if not code or not question or results is None:
            return Response({"error": "Missing required data."}, status=status.HTTP_400_BAD_REQUEST)

        if not isinstance(results, list):
            return Response({"error": "Field 'results' must be a list of test cases."}, status=status.HTTP_400_BAD_REQUEST)

        if not results:
            return Response({"error": "No test cases provided for grading."}, status=status.HTTP_400_BAD_REQUEST)

        # Filter public testcases only
        public_testcases = [
            {
                "input": tc["input"],
                "expected_output": tc["expected_output"],
                "user_output": tc["output"]
            }
            for tc in results
            if not tc.get("is_hidden", False)
        ]

        if not public_testcases:
            return Response({"error": "No public testcases available for grading."}, status=status.HTTP_400_BAD_REQUEST)

        ai_response = generate_grading_json(code, question, public_testcases)

        logger.info(f"Raw AI response: {ai_response}")

        if isinstance(ai_response, str):
            cleaned_response = re.sub(r"```json?\n(.+?)```", r"\1", ai_response, flags=re.DOTALL).strip()
            if not cleaned_response:
                logger.error("AI response is empty after cleaning")
                return Response({"error": "AI returned empty response"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            grading_data = json.loads(cleaned_response)

        elif isinstance(ai_response, dict):
            grading_data = ai_response  # Already parsed

        else:
            logger.error(f"Unexpected AI response type: {type(ai_response)}")
            return Response({"error": "Invalid response type from AI"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(grading_data, status=status.HTTP_200_OK)

    except json.JSONDecodeError:
        logger.exception("Failed to parse AI response as JSON")
        return Response({"error": "AI returned invalid JSON"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        logger.exception("Unexpected error while grading code")
        return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def run_code(request):
    """
    Wrapper view that passes request data to the core logic.
    """
    try:
        result = run_code_logic(request.data)
        status = result.pop("status_code", 200)
        return Response(result, status=status)
    except Exception as e:
        logger.error(f"run_code failed: {e}")
        return Response({"error": "Internal Server Error"}, status=500)
    

    
@api_view(['GET'])
def get_question(request: Request, pk: int) -> Response:
    """
    Retrieve a single coding question by its primary key (ID).

    Args:
        request: The HTTP request object.
        pk (int): The primary key (ID) of the question.

    Returns:
        Response: Serialized question data if found, or 404 error if not.
    """
    logger.info(f"Fetching question with ID: {pk}")
    try:
        question = Question.objects.get(pk=pk)
    except Question.DoesNotExist:
        logger.warning(f"Question not found for ID: {pk}")
        return Response({"error": "Question not found"}, status=404)

    serializer = QuestionSerializer(question)
    return Response(serializer.data)


@api_view(['GET'])
def list_questions(request: Request) -> Response:
    """
    Retrieve a list of all coding questions.

    Args:
        request: The HTTP request object.

    Returns:
        Response: List of serialized questions.
    """
    questions = Question.objects.all()
    logger.info(f"Fetched all questions. Count: {questions.count()}")
    serializer = QuestionSerializer(questions, many=True)
    return Response(serializer.data)


# Optional class-based views for detailed or list views (if you prefer CBVs)

class QuestionDetailView(APIView):
    """
    Class-based view for retrieving a single question by ID.
    """
    def get(self, request: Request, pk: int) -> Response:

        """
        Retrieve a question by its primary key (ID).

        Args:
            request: The HTTP request object.
            pk (int): The primary key of the question.

        Returns:
            Response: Serialized question data or 404 if not found.
        """
        logger.info(f"Fetching question with ID: {pk}")
        try:
            question = Question.objects.get(pk=pk)
        except Question.DoesNotExist:
            return Response({"error": "Question not found"}, status=404)
        serializer = QuestionSerializer(question)
        return Response(serializer.data)


class QuestionListView(APIView):
    """
    Class-based view for retrieving a list of all questions.
    """
    def get(self, request: Request) -> Response:

        """
        Retrieve all coding questions.

        Args:
            request: The HTTP request object.

        Returns:
            Response: A list of serialized questions.
        """
        questions = Question.objects.all()
        serializer = QuestionSerializer(questions, many=True)
        return Response(serializer.data)


from .models import CodeSubmission
from .serializers import CodeSubmissionSerializer

class CodeSubmissionViewSet(viewsets.ModelViewSet):
    """
    API endpoint for managing code submissions.
    """
    serializer_class = CodeSubmissionSerializer
    permission_classes = [] # Adjust based on auth requirements

    def get_queryset(self):
        # Return all submissions for now, or filter by user if authenticated
        user = self.request.user
        if user.is_authenticated:
            return CodeSubmission.objects.filter(user=user)
        return CodeSubmission.objects.all() 

    def perform_create(self, serializer):
        # Automatically set the user if authenticated
        if self.request.user.is_authenticated:
            serializer.save(user=self.request.user)
        else:
            # For anonymous users (dev mode/testing), assign to the first available user or create a placeholder
            from authentication.models import User
            fallback_user = User.objects.first()
            if fallback_user:
                serializer.save(user=fallback_user)
            else:
                # If no users exist at all, we can't save.
                raise serializers.ValidationError({"detail": "Authentication required and no fallback user found."})
