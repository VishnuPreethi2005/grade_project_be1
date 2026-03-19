from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q, Count
from django.utils import timezone
from django.db import transaction

from .models import (
    TestDelegation,
    EvaluationAssignment,
    Test,
    StudentAnswer,
    TestAssignment
)
from authentication.models import User
from authentication.utils import log_audit
from .delegation_serializers import (
    TestDelegationSerializer,
    EvaluationAssignmentSerializer,
    CreateDelegationSerializer,
    DelegationStatsSerializer
)
import logging

logger = logging.getLogger(__name__)


class DelegationViewSet(viewsets.ViewSet):
    """
    ViewSet for managing test delegations and evaluation assignments.
    Handles test-level delegation where Course Incharges delegate entire tests to evaluators.
    """
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=['post'], url_path='delegate-test')
    def delegate_test(self, request):
        """
        Delegate a test to one or more evaluators.
        
        POST /api/organization/delegations/delegate-test/
        Body: {
            "test_id": 123,
            "evaluator_ids": [45, 67]
        }
        """
        logger.info(f"Delegation request from user {request.user.id}")
        
        serializer = CreateDelegationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({
                "status": "error",
                "message": "Invalid data",
                "errors": serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)
        
        test_id = serializer.validated_data['test_id']
        evaluator_ids = serializer.validated_data['evaluator_ids']
        
        try:
            # Check if user has permission to delegate this test
            test = Test.objects.get(id=test_id)
            
            # Verify user is admin of the organization
            if not (request.user.organization == test.organization and 
                    request.user.role_org == 'admin'):
                return Response({
                    "status": "error",
                    "message": "You don't have permission to delegate this test"
                }, status=status.HTTP_403_FORBIDDEN)
            
            created_delegations = []
            evaluation_assignments = []
            
            with transaction.atomic():
                # Create TestDelegation entries
                for evaluator_id in evaluator_ids:
                    evaluator = User.objects.get(id=evaluator_id)
                    
                    # Check if delegation already exists
                    delegation, created = TestDelegation.objects.get_or_create(
                        test=test,
                        user=evaluator,
                        defaults={'role_type': 'EVALUATOR'}
                    )
                    
                    if created:
                        created_delegations.append(delegation)
                        logger.info(f"Created delegation: Test {test_id} -> Evaluator {evaluator_id}")
                    
                    #  Get all submitted answers for this test
                    submitted_assignments = TestAssignment.objects.filter(
                        test=test,
                        status='SUBMITTED'
                    )
                    
                    # Create EvaluationAssignment for each submitted answer
                    for assignment in submitted_assignments:
                        # Get student answers for this assignment
                        student_answers = StudentAnswer.objects.filter(
                            test=test,
                            student=assignment.student,
                            is_evaluated=False
                        )
                        
                        for answer in student_answers:
                            eval_assignment, eval_created = EvaluationAssignment.objects.get_or_create(
                                test=test,
                                student_answer=answer,
                                evaluator=evaluator,
                                defaults={'status': 'PENDING'}
                            )
                            
                            if eval_created:
                                evaluation_assignments.append(eval_assignment)
            
            return Response({
                "status": "success",
                "message": f"Test delegated to {len(created_delegations)} evaluator(s)",
                "data": {
                    "test_id": test_id,
                    "delegations_created": len(created_delegations),
                    "evaluation_assignments_created": len(evaluation_assignments),
                    "delegations": TestDelegationSerializer(created_delegations, many=True).data
                }
            }, status=status.HTTP_201_CREATED)
            
        except Test.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Test not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except User.DoesNotExist:
            return Response({
                "status": "error",
                "message": "One or more evaluators not found"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error delegating test: {e}", exc_info=True)
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='my-delegations')
    def my_delegations(self, request):
        """
        Get all delegations created by the current user.
        
        GET /api/organization/delegations/my-delegations/
        """
        try:
            # Get tests from user's organization
            delegations = TestDelegation.objects.filter(
                test__organization=request.user.organization
            ).select_related('test', 'user').order_by('-created_at')
            
            serializer = TestDelegationSerializer(delegations, many=True)
            
            return Response({
                "status": "success",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching delegations: {e}", exc_info=True)
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='assigned-to-me')
    def assigned_to_me(self, request):
        """
        Get all evaluation assignments assigned to the current user (evaluator).
        
        GET /api/organization/delegations/assigned-to-me/
        Query params:
            - status: PENDING, IN_PROGRESS, COMPLETED
        """
        try:
            query_status = request.query_params.get('status', None)
            
            assignments = EvaluationAssignment.objects.filter(
                evaluator=request.user
            ).select_related('test', 'student_answer__student', 'student_answer__question')
            
            if query_status:
                assignments = assignments.filter(status=query_status)
            
            assignments = assignments.order_by('-assigned_at')
            
            serializer = EvaluationAssignmentSerializer(assignments, many=True)
            
            return Response({
                "status": "success",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching assigned evaluations: {e}", exc_info=True)
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=True, methods=['put'], url_path='update-status')
    def update_status(self, request, pk=None):
        """
        Update the status of an evaluation assignment.
        
        PUT /api/organization/delegations/{id}/update-status/
        Body: {"status": "IN_PROGRESS" | "COMPLETED"}
        """
        try:
            assignment = EvaluationAssignment.objects.get(pk=pk, evaluator=request.user)
            
            new_status = request.data.get('status')
            if new_status not in ['PENDING', 'IN_PROGRESS', 'COMPLETED']:
                return Response({
                    "status": "error",
                    "message": "Invalid status. Must be PENDING, IN_PROGRESS, or COMPLETED"
                }, status=status.HTTP_400_BAD_REQUEST)
            
            assignment.status = new_status
            if new_status == 'COMPLETED':
                assignment.completed_at = timezone.now()
            assignment.save()
            
            return Response({
                "status": "success",
                "message": "Status updated successfully",
                "data": EvaluationAssignmentSerializer(assignment).data
            }, status=status.HTTP_200_OK)
            
        except EvaluationAssignment.DoesNotExist:
            return Response({
                "status": "error",
                "message": "Evaluation assignment not found or you don't have permission"
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error updating status: {e}", exc_info=True)
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='stats')
    def stats(self, request):
        """
        Get delegation statistics for the organization.
        
        GET /api/organization/delegations/stats/
        """
        try:
            # Total delegations in organization
            total_delegations = TestDelegation.objects.filter(
                test__organization=request.user.organization
            ).count()
            
            # Evaluation assignment stats
            eval_stats = EvaluationAssignment.objects.filter(
                test__organization=request.user.organization
            ).aggregate(
                total=Count('id'),
                pending=Count('id', filter=Q(status='PENDING')),
                in_progress=Count('id', filter=Q(status='IN_PROGRESS')),
                completed=Count('id', filter=Q(status='COMPLETED'))
            )
            
            # Unique evaluators count
            total_evaluators = TestDelegation.objects.filter(
                test__organization=request.user.organization
            ).values('user').distinct().count()
            
            stats_data = {
                "total_delegations": total_delegations,
                "pending_evaluations": eval_stats['pending'] or 0,
                "in_progress_evaluations": eval_stats['in_progress'] or 0,
                "completed_evaluations": eval_stats['completed'] or 0,
                "total_evaluators": total_evaluators
            }
            
            serializer = DelegationStatsSerializer(data=stats_data)
            serializer.is_valid()
            
            return Response({
                "status": "success",
                "data": serializer.data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching stats: {e}", exc_info=True)
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @action(detail=False, methods=['get'], url_path='available-evaluators')
    def available_evaluators(self, request):
        """
        Get list of users who are evaluators in the organization.
        
        GET /api/organization/delegations/available-evaluators/
        """
        try:
            # Get evaluators from the organization
            evaluators = User.objects.filter(
                Q(organization=request.user.organization) &
                Q(is_evaluator=True)
            ).values('id', 'email', 'username', 'full_name')
            
            return Response({
                "status": "success",
                "data": list(evaluators)
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching evaluators: {e}", exc_info=True)
            return Response({
                "status": "error",
                "message": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
