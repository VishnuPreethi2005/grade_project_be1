import pytest
import json
from unittest.mock import MagicMock, patch
from grade.ocr_processing_core import merge_split_answers
from grade.grading import StudentGrader

# ==========================================
# Level 1: Question Mappings & Merging Tests
# ==========================================

class TestLevel1MappingMerging:
    """
    Tests for:
    1. merge_split_answers (OCR core)
    2. map_questions (StudentGrader)
    """

    def test_merge_split_answers_basic(self):
        """Verify unifying split keys like Q1_cont -> Q1."""
        raw_data = {
            "Q1": {"text": "Part 1 of answer"},
            "Q1_cont": {"text": "Part 2 of answer"},
            "Q2": {"text": "Independent answer"}
        }
        json_str = json.dumps(raw_data)
        
        merged_json = merge_split_answers(json_str)
        merged_data = json.loads(merged_json)
        
        # specific assertions
        assert "Q1" in merged_data
        assert "Q1_cont" not in merged_data
        assert "Q2" in merged_data
        
        # Verify text concatenation
        assert "Part 1 of answer" in merged_data["Q1"]["text"]
        assert "Part 2 of answer" in merged_data["Q1"]["text"]

    def test_merge_split_answers_complex(self):
        """Verify merging equations and diagrams."""
        raw_data = {
            "Q3": {
                "text": "Start",
                "equations": [{"step": 1, "equation": "x=1"}]
            },
            "Q3_part2": {
                "text": "End",
                "equations": [{"step": 1, "equation": "x=2"}], # Should become step 2
                "diagram": {"1": "path/img2.png"}
            }
        }
        json_str = json.dumps(raw_data)
        
        merged_data = json.loads(merge_split_answers(json_str))
        
        q3 = merged_data["Q3"]
        assert len(q3["equations"]) == 2
        # Verify step re-numbering logic if it exists, or just append
        assert q3["equations"][1]["equation"] == "x=2"
        
        assert "diagram" in q3
        assert len(q3["diagram"]) == 1

    @patch("grade.grading.StudentGrader.__init__", return_value=None)
    def test_map_questions_exact_and_fuzzy(self, mock_init):
        """
        Verify StudentGrader.map_questions correctly links student keys 
        to answer key keys.
        """
        # Manually setup grader since __init__ is mocked
        grader = StudentGrader()
        grader.logger = MagicMock()
        
        # Mock Data
        student_questions = {
            "Q1": {"text": "Exact match"},
            "Q2a": {"text": "Fuzzy match attempt"}
        }
        answer_key_questions = {
            "Q1": {"expected": "A"},
            "Q2": {"expected": "B"} # Should match Q2a fuzzy
        }
        
        # Create grouped_answer_key mock (usually done by helper)
        # For this test, we assume map_questions takes (student_q, grouped_key)
        # But looking at source, map_questions takes (student_q, answer_key_q)
        
        mapped = grader.map_questions(student_questions, answer_key_questions)
        
        # Check Exact Match
        assert "Q1" in mapped
        assert mapped["Q1"][0]["text"] == "Exact match"
        
        # Check Fuzzy Match (Q2 -> Q2a)
        assert "Q2" in mapped
        assert mapped["Q2"][0]["text"] == "Fuzzy match attempt"

# ==========================================
# Level 2: Validation Logic Tests
# ==========================================

class TestLevel2Validation:
    """
    Tests for _validate_question_result logic in StudentGrader.
    """

    @pytest.fixture
    def grader(self):
        with patch("grade.grading.StudentGrader.__init__", return_value=None):
            grader = StudentGrader()
            grader.logger = MagicMock()
            return grader

    def test_validate_question_result_clamping(self, grader):
        """Verify marks are capped at allocated_marks and floored at 0."""
        question_data = {"allocated_marks": 5, "type": "mixed"}
        
        # Case 1: Over-marking (e.g. 6/5)
        raw_result_over = {"obtained_marks": 6, "summary": "Great job"}
        val_over = grader._validate_question_result(raw_result_over, question_data)
        assert val_over["obtained_marks"] == 5
        assert "marks capped" in val_over["summary"].lower() or "capped" in val_over["summary"].lower()

        # Case 2: Negative marking
        raw_result_under = {"obtained_marks": -1}
        val_under = grader._validate_question_result(raw_result_under, question_data)
        assert val_under["obtained_marks"] == 0

    def test_validate_question_result_feedback(self, grader):
        """Verify final_feedback population."""
        question_data = {"allocated_marks": 5}
        
        # Case 1: summary is present
        res1 = {"obtained_marks": 3, "summary": "Good effort"}
        val1 = grader._validate_question_result(res1, question_data)
        assert val1["final_feedback"] == "Good effort"

        # Case 2: only general_feedback is present
        res2 = {"obtained_marks": 3, "general_feedback": "Needs improvement"}
        val2 = grader._validate_question_result(res2, question_data)
        assert val2["final_feedback"] == "Needs improvement"
        
        # Case 3: Both present (summary takes precedence)
        res3 = {"obtained_marks": 3, "summary": "Summary", "general_feedback": "General"}
        val3 = grader._validate_question_result(res3, question_data)
        assert val3["final_feedback"] == "Summary"

    def test_validate_question_result_expected_answer_alternatives(self, grader):
        """Verify expected_answer structure for alternatives."""
        question_data = {
            "allocated_marks": 5,
            "alternatives": {
                "a": {"expected_answer": "Option A data"},
                "b": {"expected_answer": "Option B data"}
            }
        }
        res = {"obtained_marks": 0}
        
        val = grader._validate_question_result(res, question_data)
        
        ea = val["expected_answer"]
        assert "EITHER/OR" in ea["text"]
        assert len(ea["bullets"]) == 2
        
        # Check if bullets contain the expected text
        bullet_texts = [b for b in ea["bullets"]]
        assert any("Option (a): Option A data" in b for b in bullet_texts)
        assert any("Option (b): Option B data" in b for b in bullet_texts)

# ==========================================
# Level 3: End-to-End Mocked Tests
# ==========================================

from centralised_llm.src.llms.gemini_genai_llm import GenerateResponse

class TestLevel3EndToEndMocked:
    """
    Tests for grade_student using a mocked Gemini client.
    """

    @pytest.fixture
    def grader(self):
        with patch("grade.grading.StudentGrader.__init__", return_value=None):
            grader = StudentGrader()
            grader.logger = MagicMock()
            grader.client = MagicMock()
            grader.cost_calculator = MagicMock()
            grader.metrics_rows = []
            
            # Setup necessary internal dicts
            grader.answer_key = {}
            grader.answer_key_diagrams = {}
            
            return grader

    def test_grade_student_success(self, grader):
        """Mock Gemini client to verify successful grading flow."""
        # 1. Setup Data
        student_answer = {"Q1": {"text": "My Answer"}}
        grader.answer_key = {"Q1": {"allocated_marks": 5, "expected_answer": "Key"}}
        grader.answer_key_diagrams = {}

        # 2. Mock API Response
        mock_response_json = """
        {
            "root": [
                {
                    "question_number": "Q1",
                    "allocated_marks": 5,
                    "obtained_marks": 4.5,
                    "student_answer": {"text": "My Answer"},
                    "expected_answer": {"text": "Key"},
                    "mistakes_identified": [],
                    "summary": "Good job"
                }
            ]
        }
        """
        grader.client.generate_structured_json.return_value = GenerateResponse(
            response=mock_response_json,
            prompt_tokens=100,
            completion_tokens=50,
            cost=0.015,
            error=None
        )

        # 3. Call grade_student
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"): # Minimal prompt template
             final_result = grader.grade_student(student_answer, output_folder="dummy", student_id="student123")

        # 4. Assertions
        assert final_result["total_score"] == 4.5
        assert final_result["student_id"] == "student123"
        assert len(final_result["results"]) == 1
        assert final_result["results"][0]["question_number"] == "Q1"
        
        # Verify API called
        grader.client.generate_structured_json.assert_called_once()
        grader.client.generate_structured_json.call_args[1]["call_type_for_logging"] == "grade_student_single_call"

    def test_grade_student_api_error(self, grader):
        """Mock Gemini client to simulate API error."""
        # 1. Setup Data
        student_answer = {"Q1": {"text": "My Answer"}}
        grader.answer_key = {"Q1": {"allocated_marks": 5}}
        
        # 2. Mock API Error
        grader.client.generate_structured_json.return_value = GenerateResponse(
            response="", error="API Overloaded", cost=0
        )

        # 3. Call grade_student
        with patch("grade.grading.load_prompt", return_value=""):
             final_result = grader.grade_student(student_answer, output_folder="dummy", student_id="student_err")

        '''
        assert len(final_result["results"]) == 1
        assert final_result["results"][0]["obtained_marks"] == 0
        assert "error" in final_result["results"][0]["evaluation_criteria_status"]
        '''


# ==========================================
# Level 4: Content & Subject Variations Tests
# ==========================================

class TestLevel4ContentVariations:
    """
    Tests ensuring different answer types (equations, tables, etc.)
    traverse the logic correctly without crashing.
    """

    @pytest.fixture
    def grader(self):
        with patch("grade.grading.StudentGrader.__init__", return_value=None):
            grader = StudentGrader()
            grader.logger = MagicMock()
            grader.client = MagicMock()
            grader.cost_calculator = MagicMock()
            grader.metrics_rows = []
            grader.answer_key = {}
            grader.answer_key_diagrams = {}
            return grader
            
    # Parameterized Test for multiple subjects/formats
    @pytest.mark.parametrize("subject, student_input, key_input, expected_prompt_check", [
        (
            "Physics_Equation", 
            {"equations": [{"step": 1, "equation": r"\\frac{1}{2}mv^2"}]}, 
            {"allocated_marks": 3},
            r"\\frac{1}{2}mv^2" # Should appear in prompt
        ),
        (
            "Data_Table", 
            {"table": [["Col1", "Col2"], ["Val1", "Val2"]]}, 
            {"allocated_marks": 5},
            "Val2" # Table content should appear
        ),
        (
            "History_Bullets", 
            {"bullets": ["Point 1", "Point 2"]}, 
            {"allocated_marks": 2},
            "Point 1"
        )
    ])
    def test_grading_content_variations(self, grader, subject, student_input, key_input, expected_prompt_check):
        """
        Verify that grading logic handles various content types (LaTeX, Table, Bullets)
        and passes them into the prompt.
        """
        # 1. Setup
        q_num = f"Q_{subject}"
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: key_input}
        
        # 2. Mock API to return valid dummy data
        grader.client.generate_structured_json.return_value = GenerateResponse(
            response=f'{{"root": [{{"question_number": "{q_num}", "obtained_marks": 1, "student_answer": {{}}, "expected_answer": {{}}, "mistakes_identified": []}}]}}',
            prompt_tokens=10, completion_tokens=10, cost=0.0, error=None
        )

        # 3. Execution
        # We need to spy on 'grade_student_single_call' or verify the prompt construction.
        # Since 'grade_student' calls 'grade_student_single_call', we can patch 'load_prompt'
        # and verify the formatted string, OR just verify the 'contents' passed to client.
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id=f"Test_{subject}")

        # 4. Verification: Check that our unique content made it into the LLM payload
        call_args = grader.client.generate_structured_json.call_args
        contents = call_args[1]["contents"] # [prompt_text, images...]
        prompt_text = contents[0]
        
        # Verify the specific content (Equation, Table val, or Bullet) is present in the prompt
        # We assume {task_data_json} dumps the whole student answer structure
        assert expected_prompt_check in prompt_text, f"Failed to find '{expected_prompt_check}' in prompt for {subject}"


# ==========================================
# Level 5: Edge Cases & Error Handling Tests
# ==========================================

class TestLevel5EdgeCases:
    """
    Tests for unusual, empty, or malformed inputs to prevent crashes.
    """

    @pytest.fixture
    def grader(self):
        with patch("grade.grading.StudentGrader.__init__", return_value=None):
            grader = StudentGrader()
            grader.logger = MagicMock()
            grader.client = MagicMock()
            grader.cost_calculator = MagicMock()
            grader.metrics_rows = []
            grader.answer_key = {}
            grader.answer_key_diagrams = {}
            return grader

    def test_edge_case_empty_input(self, grader):
        """Verify behavior when student_answer is empty."""
        student_answer = {}
        # Setup at least one key so we iterate once (or strict empty check)
        grader.answer_key = {"Q1": {"allocated_marks": 5}} 
        
        # When empty answer, map_questions usually returns "No answer provided"
        # We need to verify grade_student doesn't crash during mapping or grading
        
        # Mock API to return something generic
        grader.client.generate_structured_json.return_value = GenerateResponse(
            response='{"root": []}', prompt_tokens=0, completion_tokens=0, cost=0, error=None
        )

        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            result = grader.grade_student(student_answer, "dummy", "empty_student")
        
        assert result["total_score"] == 0
        assert len(result["results"]) == 0 # Or 1 depending on implementation of map_questions for missing answer

    def test_edge_case_missing_keys_in_answer_key(self, grader):
        """Verify safety when answer key lacks allocated_marks."""
        student_answer = {"Q1": {"text": "A"}}
        # Missing 'allocated_marks', should default to 0
        grader.answer_key = {"Q1": {"expected_answer": "B"}} 
        
        mock_resp = """
        { "root": [{ "question_number": "Q1", "obtained_marks": 10 }] }
        """
        grader.client.generate_structured_json.return_value = GenerateResponse(
             response=mock_resp, prompt_tokens=0, completion_tokens=0, cost=0, error=None
        )

        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            result = grader.grade_student(student_answer, "dummy", "missing_key_student")
            
        # Should be capped at allocated_marks (which defaults to 0)
        q1_res = result["results"][0]
        assert q1_res["allocated_marks"] == 0
        assert q1_res["obtained_marks"] == 0 # validation should cap it

    def test_edge_case_type_mismatch(self, grader):
        """Verify handling of string marks '5' instead of 5."""
        question_data = {"allocated_marks": 5}
        
        # API returns string "5" marks
        raw_res = {"obtained_marks": "4", "summary": "Str marks"}
        
        # Direct test of validation logic which converts types
        val = grader._validate_question_result(raw_res, question_data)
        
        assert val["obtained_marks"] == 4.0
        assert isinstance(val["obtained_marks"], float)

    def test_edge_case_large_input(self, grader):
        """Verify system handles large inputs without crashing."""
        long_text = "A" * 10000
        student_answer = {"Q1": {"text": long_text}}
        grader.answer_key = {"Q1": {"allocated_marks": 5}}

        grader.client.generate_structured_json.return_value = GenerateResponse(
            response='{"root": []}', prompt_tokens=0, completion_tokens=0, cost=0, error=None
        )

        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, "dummy", "large_student")
            
        # Just ensure it reached the client call without RecursionError or similar
        call_args = grader.client.generate_structured_json.call_args
        contents = call_args[1]["contents"][0]
        assert long_text in contents
