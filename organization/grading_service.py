import logging
import json
import os
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from grade.grading import StudentGrader
from grade.models import GradingResult, QuestionGrade, CriteriaGrade
from organization.models import Test, StudentAnswer, TestAssignment, TestQuestion
from authentication.models import User

logger = logging.getLogger(__name__)

class OrganizationGradingService:
    def __init__(self, test_id):
        self.test_id = test_id
        try:
            self.test = Test.objects.get(id=test_id)
        except Test.DoesNotExist:
            raise ValueError(f"Test with id {test_id} does not exist")

    def grade_test(self):
        """
        Main method to trigger AI grading for all eligible student answers in the test.
        """
        logger.info(f"Starting AI grading for Test: {self.test.title} ({self.test.id})")

        # 1. Validate Question Paper and Answer Key
        try:
            question_paper = self.test.question_paper
        except Exception:
            raise ValueError("Test does not have a linked Question Paper.")

        if not question_paper.answer_key:
            raise ValueError("Question Paper does not have an uploaded Answer Key.")

        # Ensure answer key file exists
        if not os.path.exists(question_paper.answer_key.path):
             raise ValueError(f"Answer Key file not found at: {question_paper.answer_key.path}")
        
        # 2. Initialize StudentGrader
        # We pass None for answer_upload since we are grading StudentAnswers directly
        grader = StudentGrader(answer_upload=None)
        
        # Load Answer Key
        try:
            answer_key, answer_key_diagrams = grader.load_answer_key(question_paper.answer_key.path)
        except Exception as e:
            raise ValueError(f"Failed to load Answer Key: {e}")

        # 3. Fetch all students assigned to this test
        assignments = TestAssignment.objects.filter(test=self.test)
        
        results_summary = {
            "total_students": assignments.count(),
            "graded_count": 0,
            "errors": []
        }

        # 4. Iterate and Grade per Student
        for assignment in assignments:
            student = assignment.student
            logger.info(f"Processing grading for Student: {student.email}")
            
            try:
                self._grade_single_student(student, grader, answer_key, answer_key_diagrams)
                results_summary["graded_count"] += 1
            except Exception as e:
                logger.error(f"Failed to grade student {student.email}: {e}", exc_info=True)
                results_summary["errors"].append(f"{student.email}: {str(e)}")

        return results_summary

    def _grade_single_student(self, student, grader, answer_key, answer_key_diagrams):
        """
        Grades a single student's answers for the test.
        """
        # Fetch all answers for this student for this test
        student_answers = StudentAnswer.objects.filter(
            test=self.test, 
            student=student
        ).select_related('question')

        if not student_answers.exists():
            logger.info(f"No answers submitted by {student.email}")
            return

        # Prepare 'mapped_questions' structure expected by StudentGrader
        mapped_questions = {}
        student_ans_map = {} 

        for sa in student_answers:
            # Heuristic: Use Question Order as Q number (e.g. 1 -> "Q1")
            q_key = f"Q{sa.question.order}"
            
            # Construct student answer dict structure expected by Grader
            student_val = {"text": sa.answer_text}
            
            # Check if this key exists in Answer Key
            if q_key in answer_key:
                mapped_questions[q_key] = (student_val, answer_key[q_key])
                student_ans_map[q_key] = sa
            else:
                logger.warning(f"Question {q_key} not found in Answer Key for test {self.test.id}")

        if not mapped_questions:
            logger.warning("No mapped questions found. Check Question Order matching.")
            return

        # Call the grader logic
        grading_results_list = grader.grade_student_single_call(
            mapped_questions=mapped_questions,
            student_diagrams={}, 
            answer_key_diagrams=answer_key_diagrams
        )

        # Process Results and Save to DB
        with transaction.atomic():
            total_score = 0
            
            for result_item in grading_results_list:
                q_num = result_item.get("question_number") # e.g. "Q1"
                
                # Find the corresponding StudentAnswer model
                sa_model = student_ans_map.get(q_num)
                
                if sa_model:
                    obtained_marks = result_item.get("obtained_marks", 0)
                    
                    # Update StudentAnswer Model
                    sa_model.score = obtained_marks
                    sa_model.is_evaluated = True
                    sa_model.save()
                    
                    total_score += obtained_marks

            # Update TestAssignment with total score
            assignment = TestAssignment.objects.get(test=self.test, student=student)
            assignment.score = total_score
            assignment.status = "COMPLETED"
            assignment.save()
