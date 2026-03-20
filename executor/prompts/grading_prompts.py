def build_grading_prompt(code, question, public_testcases):
    formatted_cases = ""
    for i, case in enumerate(public_testcases, 1):
        formatted_cases += f"\n--- Test Case {i} ---\nInput:\n{case['input']}\nExpected Output:\n{case['expected_output']}\nUser Output:\n{case['user_output']}\n"

    return f"""
You are an AI code grader. Evaluate the following code submission based on the following **rubric (out of 10 marks)**:

1. **Code Compiles/Runs** (0–2): Does the code run without syntax/runtime errors?
2. **Correctness of Logic** (0–3): Does the logic implement the intended behavior and handle expected cases?
3. **Output Accuracy** (0–1): Does the output match the problem requirements exactly?
4. **Code Readability** (0–1): Clear indentation, meaningful naming, and good structure.
5. **Use of Language Features** (0–1): Proper use of constructs like loops, conditionals, functions, OOP, etc.
6. **Comments and Documentation** (0–1): Are important logic sections well explained?
7. **Error Handling / Edge Cases** (0–1): Does it handle invalid inputs or edge cases gracefully?

Additionally, analyze and estimate:
- The **best-case** and **worst-case time complexity** of the problem based on the problem description.
- The **time complexity of the submitted user code**, along with **justification**.

Return your evaluation in the following JSON format:
{{
  "code_compiles": {{"score": int, "feedback": str}},
  "logic_correctness": {{"score": int, "feedback": str}},
  "output_accuracy": {{"score": int, "feedback": str}},
  "readability": {{"score": int, "feedback": str}},
  "language_features": {{"score": int, "feedback": str}},
  "documentation": {{"score": int, "feedback": str}},
  "error_handling": {{"score": int, "feedback": str}},
  "final_score": int,
  "summary": str,
  "strengths": str,
  "weaknesses": str,
  "time_complexity": {{
    "problem_best_case": str,
    "problem_worst_case": str,
    "code_complexity": {{
      "estimated": str,
      "justification": str
    }}
  }},
  "concepts_covered": ["concept1", "concept2"]
}}

### Problem Description:
{question}

### User's Code:
{code}

### Public Test Cases:
{formatted_cases}
"""
