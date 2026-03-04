"""
Test Suite for AI Grading Pipeline - Subject-Specific Tests

Comprehensive tests ensuring grading works for all subjects:
Physics, Chemistry, Biology, Maths, English, Accounts, Business Studies.

Tests focus on content types: equations, tables, bullets, diagrams, text.
"""

import pytest
import json
from unittest.mock import MagicMock, patch
from grade.grading import StudentGrader
from centralised_llm.src.llms.gemini_genai_llm import GenerateResponse


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def grader():
    """Create a mocked StudentGrader for testing."""
    with patch("grade.grading.StudentGrader.__init__", return_value=None):
        grader = StudentGrader()
        grader.logger = MagicMock()
        grader.client = MagicMock()
        grader.cost_calculator = MagicMock()
        grader.metrics_rows = []
        grader.answer_key = {}
        grader.answer_key_diagrams = {}
        return grader


def create_mock_response(question_number, obtained_marks, allocated_marks):
    """Helper to create mock API response."""
    response_json = json.dumps({
        "root": [{
            "question_number": question_number,
            "allocated_marks": allocated_marks,
            "obtained_marks": obtained_marks,
            "student_answer": {},
            "expected_answer": {},
            "mistakes_identified": [],
            "summary": "Graded successfully"
        }]
    })
    return GenerateResponse(
        response=response_json,
        prompt_tokens=100,
        completion_tokens=50,
        cost=0.01,
        error=None
    )


# =============================================================================
# Test Class: Subject-Specific Content Types
# =============================================================================

class TestSubjectSpecificGrading:
    """
    Tests ensuring different subject content types are correctly processed
    through the grading pipeline.
    """

    # -------------------------------------------------------------------------
    # Physics Tests - Equations, Diagrams, Numerical
    # -------------------------------------------------------------------------
    
    @pytest.mark.parametrize("student_input, expected_in_prompt", [
        # Kinematics equation
        ({"equations": [{"step": 1, "equation": r"v = u + at"}]}, r"v = u + at"),
        # Newton's law formula
        ({"equations": [{"step": 1, "equation": r"F = ma"}]}, r"F = ma"),
        # With text explanation
        ({"text": "Using kinematic equation", "equations": [{"step": 1, "equation": r"s = ut + \frac{1}{2}at^2"}]}, 
         r"s = ut"),
    ])
    def test_physics_equations_in_prompt(self, grader, student_input, expected_in_prompt):
        """Physics: Verify equations are included in grading prompt."""
        q_num = "Q1"
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 3, "evaluation_criteria": ["Correct formula (1)"]}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 3, 3)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="physics_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        assert expected_in_prompt in prompt_text, f"Physics equation not found in prompt"

    # -------------------------------------------------------------------------
    # Chemistry Tests - Chemical Equations, Reactions, Tables
    # -------------------------------------------------------------------------
    
    @pytest.mark.parametrize("student_input, expected_in_prompt", [
        # Chemical equation
        ({"text": "Saponification reaction", "equations": [{"step": 1, "equation": r"NaOH + RCOOH → RCOONa + H2O"}]}, 
         "NaOH"),
        # Reaction mechanism
        ({"bullets": ["Step 1: Nucleophilic attack", "Step 2: Elimination"]}, "Nucleophilic attack"),
    ])
    def test_chemistry_content_in_prompt(self, grader, student_input, expected_in_prompt):
        """Chemistry: Verify chemical equations and reactions are processed."""
        q_num = "Q1"
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 2, "evaluation_criteria": []}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 2, 2)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="chemistry_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        assert expected_in_prompt in prompt_text

    # -------------------------------------------------------------------------
    # Biology Tests - Bullets, Diagrams, Process Descriptions
    # -------------------------------------------------------------------------
    
    def test_biology_bullets_in_prompt(self, grader):
        """Biology: Verify bullet points (cell parts, processes) are processed."""
        q_num = "Q1"
        student_input = {
            "bullets": ["Nucleus: Contains DNA", "Mitochondria: Powerhouse of cell", "Ribosome: Protein synthesis"]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 3, "evaluation_criteria": ["Each part (1)"]}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 3, 3)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="biology_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        assert "Nucleus" in prompt_text
        assert "Mitochondria" in prompt_text

    # -------------------------------------------------------------------------
    # Maths Tests - Step-by-step Equations, Proofs
    # -------------------------------------------------------------------------
    
    @pytest.mark.parametrize("equations_input, expected_step_count", [
        ([{"step": 1, "equation": "2x + 3 = 7"}, {"step": 2, "equation": "2x = 4"}, {"step": 3, "equation": "x = 2"}], 3),
        ([{"step": 1, "equation": r"\int x^2 dx"}, {"step": 2, "equation": r"\frac{x^3}{3} + C"}], 2),
    ])
    def test_maths_step_equations(self, grader, equations_input, expected_step_count):
        """Maths: Verify step-by-step equations are preserved."""
        q_num = "Q1"
        student_input = {"equations": equations_input}
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 3}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 3, 3)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="maths_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        
        # Verify all steps included
        for eq in equations_input:
            assert eq["equation"] in prompt_text or eq["equation"].replace("\\", "") in prompt_text

    # -------------------------------------------------------------------------
    # English Tests - Long Text, Essays, Comprehension
    # -------------------------------------------------------------------------
    
    def test_english_long_text_answer(self, grader):
        """English: Verify long essay-type answers are not truncated."""
        q_num = "Q1"
        long_essay = "The author uses metaphor extensively throughout the passage to convey " + \
                     "the theme of isolation. " * 50  # Create long text
        student_input = {"text": long_essay}
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 5, "evaluation_criteria": ["Theme analysis (2)", "Examples (2)", "Expression (1)"]}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 4, 5)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="english_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        
        # Verify long text is present (not truncated)
        assert "metaphor" in prompt_text
        assert "isolation" in prompt_text

    def test_english_comprehension_bullets(self, grader):
        """English: Verify comprehension answer with bullets."""
        q_num = "Q1"
        student_input = {
            "text": "The poem explores themes of nature and solitude.",
            "bullets": [
                "Imagery: 'golden daffodils' symbolizes hope",
                "Personification: 'dancing in the breeze'",
                "Mood: Contemplative and serene"
            ]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 4}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 4, 4)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="english_comp_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        assert "daffodils" in prompt_text
        assert "Personification" in prompt_text

    # -------------------------------------------------------------------------
    # Accounts Tests - Journal, Ledger, Trial Balance (Tables)
    # -------------------------------------------------------------------------
    
    def test_accounts_journal_entry_table(self, grader):
        """Accounts: Verify Journal Entry table format is processed."""
        q_num = "Q1"
        student_input = {
            "text": "Journal Entry for Capital Introduction",
            "tables": [{
                "heading": ["Date", "Particulars", "L.F.", "Debit (₹)", "Credit (₹)"],
                "rows": [
                    ["2023 Apr 1", "Cash A/c Dr.", "", "50,000", ""],
                    ["", "To Capital A/c", "", "", "50,000"],
                    ["", "(Capital introduced)", "", "", ""]
                ]
            }]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {
            "allocated_marks": 3,
            "type": "table",
            "evaluation_criteria": ["Correct Dr/Cr entries (2)", "Narration (1)"]
        }}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 3, 3)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="accounts_journal_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        
        assert "Cash A/c" in prompt_text or "Cash" in prompt_text
        assert "Capital" in prompt_text
        assert "50,000" in prompt_text or "50000" in prompt_text

    def test_accounts_trial_balance_table(self, grader):
        """Accounts: Verify Trial Balance format is processed."""
        q_num = "Q1"
        student_input = {
            "text": "Trial Balance as on 31st March 2023",
            "tables": [{
                "heading": ["Particulars", "L.F.", "Debit (₹)", "Credit (₹)"],
                "rows": [
                    ["Cash A/c", "1", "30,000", ""],
                    ["Capital A/c", "1", "", "50,000"],
                    ["Purchases A/c", "2", "20,000", ""],
                    ["Total", "", "50,000", "50,000"]
                ]
            }]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 4}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 4, 4)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="accounts_trial_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        assert "Trial Balance" in prompt_text or "Debit" in prompt_text

    def test_accounts_ledger_format(self, grader):
        """Accounts: Verify Ledger T-format is processed."""
        q_num = "Q1"
        student_input = {
            "text": "Cash Account (Ledger)",
            "tables": [
                # Dr. Side
                {
                    "heading": ["Date", "Particulars", "J.F.", "Amount"],
                    "rows": [["Apr 1", "To Capital", "1", "50,000"]]
                },
                # Cr. Side
                {
                    "heading": ["Date", "Particulars", "J.F.", "Amount"],
                    "rows": [["Apr 5", "By Purchases", "2", "20,000"]]
                }
            ]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 4, "type": "table"}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 4, 4)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="accounts_ledger_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        assert "Purchases" in prompt_text or "purchases" in prompt_text

    # -------------------------------------------------------------------------
    # Business Studies Tests - SWOT, Case Study, Marketing Mix
    # -------------------------------------------------------------------------
    
    def test_business_swot_analysis(self, grader):
        """Business Studies: Verify SWOT analysis is processed."""
        q_num = "Q1"
        student_input = {
            "text": "SWOT Analysis of ABC Ltd.",
            "bullets": [
                "Strengths: Strong brand reputation, loyal customer base",
                "Weaknesses: High debt, limited product range",
                "Opportunities: Emerging markets, digital transformation",
                "Threats: Intense competition, regulatory changes"
            ]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {
            "allocated_marks": 4,
            "evaluation_criteria": ["Each SWOT component (1)"]
        }}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 4, 4)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="business_swot_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        assert "Strengths" in prompt_text
        assert "Weaknesses" in prompt_text
        assert "Opportunities" in prompt_text
        assert "Threats" in prompt_text

    def test_business_case_study_answer(self, grader):
        """Business Studies: Verify case study answer format."""
        q_num = "Q1"
        student_input = {
            "text": """The passage illustrates the principle of 'Division of Work' by Fayol.
            
Quoted line: "Each worker was assigned a specific task based on their expertise."

Explanation: Division of Work leads to specialization, which improves efficiency and 
productivity. When workers focus on a single task, they develop expertise and can 
perform better.""",
            "bullets": [
                "Principle identified: Division of Work",
                "Quote from passage: Each worker assigned specific task",
                "Benefit: Increased efficiency and expertise"
            ]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {
            "allocated_marks": 4,
            "evaluation_criteria": ["Correct principle (1)", "Relevant quote (1)", "Explanation (2)"]
        }}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 4, 4)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="business_case_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        assert "Division of Work" in prompt_text
        assert "specialization" in prompt_text or "expertise" in prompt_text

    def test_business_marketing_mix_4ps(self, grader):
        """Business Studies: Verify Marketing Mix (4Ps) answer."""
        q_num = "Q1"
        student_input = {
            "text": "Marketing Mix for launching a new smartphone",
            "bullets": [
                "Product: 6.5 inch display, 5G enabled, 108MP camera",
                "Price: Premium pricing strategy at ₹49,999",
                "Place: Online exclusive launch on Flipkart and Amazon",
                "Promotion: Social media campaigns, influencer marketing, launch event"
            ]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {
            "allocated_marks": 4,
            "evaluation_criteria": ["Each P explained with example (1)"]
        }}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 4, 4)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            grader.grade_student(student_answer, output_folder="dummy", student_id="business_4p_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        assert "Product" in prompt_text
        assert "Price" in prompt_text
        assert "Place" in prompt_text
        assert "Promotion" in prompt_text


# =============================================================================
# Test Class: MCQ/Objective Questions
# =============================================================================

class TestMCQGrading:
    """Tests for Multiple Choice Questions across subjects."""

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

    @pytest.mark.parametrize("subject, student_text, correct_option", [
        ("Physics", "b) 9.8 m/s²", "B"),
        ("Chemistry", "c) Mercury Cell", "C"),
        ("Maths", "a) 2.0", "A"),
        ("Biology", "d) Mitochondria", "D"),
        ("Accounts", "a) Debit balance", "A"),
        ("Business_Studies", "c) Planning", "C"),
    ])
    def test_mcq_answer_processing(self, grader, subject, student_text, correct_option):
        """Verify MCQ answers are processed for all subjects."""
        q_num = "Q1"
        student_answer = {q_num: {"text": student_text}}
        grader.answer_key = {q_num: {
            "allocated_marks": 1,
            "correct_option": correct_option,
            "expected_answer": correct_option.lower()
        }}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 1, 1)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            result = grader.grade_student(student_answer, output_folder="dummy", student_id=f"{subject}_mcq")
        
        # Verify grading completed without errors
        assert result["total_score"] >= 0
        assert len(result["results"]) == 1


# =============================================================================
# Test Class: Alternative (EITHER/OR) Questions
# =============================================================================

class TestAlternativeQuestions:
    """Tests for EITHER/OR style questions (common in CBSE)."""

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

    def test_either_or_question_physics(self, grader):
        """Test alternative questions in Physics (e.g., Q20_A / Q20_B)."""
        # Student answers Q20_B (Fuel Cell), not Q20_A (Lead Storage Battery)
        student_answer = {
            "Q20b": {
                "text": "Fuel Cell",
                "bullets": [
                    "Converts chemical energy directly to electrical energy",
                    "Example: H2-O2 fuel cell",
                    "Advantages: High efficiency, pollution-free"
                ]
            }
        }
        
        grader.answer_key = {
            "Q20_A": {
                "type": "equation",
                "allocated_marks": 2,
                "expected_answer": {"Anode": "Pb equation", "Cathode": "PbO2 equation"}
            },
            "Q20_B": {
                "type": "text",
                "allocated_marks": 2,
                "expected_answer": {"definition": "Galvanic cell...", "example": "H2O2 fuel cell"}
            }
        }
        
        grader.client.generate_structured_json.return_value = create_mock_response("Q20", 2, 2)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            result = grader.grade_student(student_answer, output_folder="dummy", student_id="either_or_test")
        
        # Should process without crashing
        assert "results" in result

    def test_either_or_question_chemistry(self, grader):
        """Test alternative questions in Chemistry."""
        student_answer = {"Q30": {"text": "Option A answer about phenol synthesis"}}
        
        grader.answer_key = {
            "Q30_A": {"allocated_marks": 3, "expected_answer": "Phenol synthesis steps"},
            "Q30_B": {"allocated_marks": 3, "expected_answer": "Lucas test for alcohols"}
        }
        
        grader.client.generate_structured_json.return_value = create_mock_response("Q30", 3, 3)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            result = grader.grade_student(student_answer, output_folder="dummy", student_id="chem_either_or")
        
        assert "results" in result


# =============================================================================
# Test Class: Edge Cases Across Subjects
# =============================================================================

class TestEdgeCasesAllSubjects:
    """Edge cases and error handling across all subjects."""

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

    def test_mixed_content_types(self, grader):
        """Test answer with all content types (comprehensive mixed answer)."""
        q_num = "Q1"
        student_input = {
            "text": "Explanation text here",
            "equations": [{"step": 1, "equation": "x = 2"}],
            "tables": [{"heading": ["A", "B"], "rows": [["1", "2"]]}],
            "bullets": ["Point 1", "Point 2"]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 5}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 5, 5)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            result = grader.grade_student(student_answer, output_folder="dummy", student_id="mixed_test")
        
        call_args = grader.client.generate_structured_json.call_args
        prompt_text = call_args[1]["contents"][0]
        
        # All content types should be in prompt
        assert "Explanation" in prompt_text
        assert "x = 2" in prompt_text
        assert "Point 1" in prompt_text

    def test_empty_content_types(self, grader):
        """Test handling of null/empty content types."""
        q_num = "Q1"
        student_input = {
            "text": "Only text provided",
            "equations": None,
            "tables": None,
            "bullets": None
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 2}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 2, 2)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            # Should not crash with None values
            result = grader.grade_student(student_answer, output_folder="dummy", student_id="null_test")
        
        assert result["total_score"] >= 0

    def test_special_characters_in_content(self, grader):
        """Test handling of special characters (LaTeX, currency symbols)."""
        q_num = "Q1"
        student_input = {
            "text": "₹50,000 invested at 10% p.a.",
            "equations": [{"step": 1, "equation": r"A = P(1 + \frac{r}{100})^n"}]
        }
        student_answer = {q_num: student_input}
        grader.answer_key = {q_num: {"allocated_marks": 3}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 3, 3)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            result = grader.grade_student(student_answer, output_folder="dummy", student_id="special_char_test")
        
        assert result["total_score"] >= 0

    @pytest.mark.parametrize("subject", [
        "Physics", "Chemistry", "Biology", "Maths", "English", "Accounts", "Business_Studies"
    ])
    def test_empty_answer_for_all_subjects(self, grader, subject):
        """Test empty answer handling across all subjects."""
        q_num = "Q1"
        student_answer = {q_num: {"text": ""}}  # Empty answer
        grader.answer_key = {q_num: {"allocated_marks": 5}}
        
        grader.client.generate_structured_json.return_value = create_mock_response(q_num, 0, 5)
        
        with patch("grade.grading.load_prompt", return_value="{task_data_json}"):
            result = grader.grade_student(student_answer, output_folder="dummy", student_id=f"{subject}_empty")
        
        # Should not crash, should return 0 marks
        assert result is not None
        assert "results" in result
