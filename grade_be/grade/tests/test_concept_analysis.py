import pytest
import json
from grade.grading import StudentGrader

@pytest.mark.django_db
class TestConceptAnalysis:
    
    def test_gravitation_derivation(self):
        print("\n\n=== RUNNING GRAVITATION DERIVATION TEST ===")
        print("Initializing StudentGrader...")
        try:
            grader = StudentGrader()
        except Exception as e:
            pytest.fail(f"Failed to init grader: {e}")

        # Sample Data: Universal Law of Gravitation (Formatted as per standard schema)
        question_num = "Q5"
        question_data = {
            "type": "text", 
            "question_note": "Derivation question.",
            "allocated_marks": 5,
            "correct_option": "",
            "criteria_status": "defined",
            "expected_answer": """Statement: Force is directly proportional to product of masses and inversely proportional to square of distance.
Formula: F = G m1 m2 / r^2
where G is universal gravitational constant.""",
            "evaluation_criteria": [
                "Statement of the law (1)",
                "Proportionality to product of masses (1)",
                "Inverse square law (distance) (1)",
                "Final Formula F = G m1m2/r^2 (1)",
                "Definition of G (1)"
            ]
        }
        
        # User provided Student answer (Exact)
        student_answer = {
            "text": """The Universal Law of Gravitation states that every object in the universe attracts every other object with a gravitational force. This force depends on the masses of the objects and the distance between them.

According to Newton, the gravitational force between two bodies is proportional to the masses of the bodies and inversely proportional to the distance between them. The relation can be written as:
F ∝ m1 m2 / r^2

By introducing a constant, the formula becomes:
F = G m1 m2 / r^2

where m1 and m2 are the masses of the two bodies, r is the distance between them, and G is the gravitational constant.

This law explains why objects fall to the Earth and why planets move around the Sun."""
        }
        
        grading_feedback = "The student correctly states the law, derives the proportionality relations, and arrives at the final formula defining all terms including G. Full marks."

        print("Running Concept Analysis for Gravitation...")
        
        try:
            result = grader.analyze_concepts_for_question(
                question_num=question_num,
                question_data=question_data,
                student_answer=student_answer,
                grading_feedback=grading_feedback
            )
            
            print("Analysis Complete!")
            print(json.dumps(result, indent=2))
            
            assert result and result.get("concepts"), "No concepts returned"
            
            # Since answer is perfect, we expect High mastery
            high_mastery_count = 0
            for c in result["concepts"]:
                if c["mastery_class"] in ["High", "Good"]:
                    high_mastery_count += 1
            
            assert high_mastery_count >= 3, "Expected mostly High/Good mastery for a correct answer"

        except Exception as e:
            pytest.fail(f"Error during analysis: {e}")

    def test_batch_analysis(self):
        print("\n\n=== RUNNING BATCH CONCEPT ANALYSIS TEST ===")
        try:
            grader = StudentGrader()
        except Exception:
            pytest.skip("Skipping batch test - grader init failed")

        # Reuse data from above for Q1
        q_data = {
            "type": "text", 
            "allocated_marks": 5,
            "evaluation_criteria": ["Concept A", "Concept B"],
            "expected_answer": "Expected explanation for A and B"
        }
        student_ans = {"text": "Student explanation for A and B"}
        
        batch_input = [
            {
                "question_num": "Q1",
                "question_data": q_data,
                "student_answer": student_ans,
                "grading_feedback": "Correct answer."
            },
            {
                "question_num": "Q2", 
                "question_data": {
                    "type": "text",
                    "allocated_marks": 2,
                    "evaluation_criteria": ["Simple Concept"],
                    "expected_answer": "Simple Definition"
                },
                "student_answer": {"text": "Simple Definition"},
                "grading_feedback": "Correct."
            }
        ]
        
        print(f"Running Batch Analysis for {len(batch_input)} questions...")
        results = grader.analyze_concepts_for_batch(batch_input)
        
        print("Batch Analysis Complete!")
        print(json.dumps(results, indent=2))
        
        assert isinstance(results, list)
        assert len(results) == 2
        
        # Verify mapping back
        q_nums = [r.get("question_number") for r in results]
        assert "Q1" in q_nums
        assert "Q2" in q_nums
        
        # Check structure
        for r in results:
            assert "concepts" in r
            assert "overall_confidence_percentage" in r

    def test_messy_criteria_normalization(self):
        print("\n\n=== RUNNING MESSY CRITERIA NORMALIZATION TEST ===")
        try:
            grader = StudentGrader()
        except Exception:
            pytest.skip("Skipping messy test - grader init failed")

        # User's exact messy example
        question_num = "Q_Messy"
        question_data = {
            "type": "text",
            "allocated_marks": 3,
            "evaluation_criteria": [
                "(i) Nernst Equation) Ecell = E0cell - 0.059/n log Q (1)",
                "(i) Substitution & calculation) 1.98V = E0cell - ... (1)",
                "(i) Result for E_cell^0) E0cell = 1.9996V (1)"
            ]
        }
        
        # Student answer with partial correctness (same as user example)
        student_answer = {
            "text": "Ecell = E0cell - 0.059/n log [P]/[R].\n1.98 = E0 - 0.059/6 log(10^-2). \nE0 = 1.98 - 0.01 = 1.97V"
        }
        
        grading_feedback = "Correct formula and substitution. Calculation error in final step."

        print("Running Analysis on Messy Criteria...")
        result = grader.analyze_concepts_for_question(
            question_num=question_num,
            question_data=question_data,
            student_answer=student_answer,
            grading_feedback=grading_feedback
        )
        
        print("Analysis Result:")
        print(json.dumps(result, indent=2))
        
        concepts = result.get("concepts", [])
        assert len(concepts) > 0
        
        # We manually check if names are cleaned up
        print("\n--- CONCEPT NAMES FOUND ---")
        for c in concepts:
            print(f"- {c['concept_name']}")
            
        # Assertion: Check that we DON'T have the messy raw text
        for c in concepts:
            name = c['concept_name'].lower()
            assert "(i)" not in name, f"Found raw index in concept name: {name}"
            assert "result for e_cell^0" not in name, f"Found raw messy text: {name}"
