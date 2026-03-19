# executor/prompts.py


def build_question_generation_prompt(topic, difficulty):
    return (
        f"Generate 5 unique and diverse coding questions on the topic '{topic}' with difficulty '{difficulty}'.\n\n"
        "Introduce randomness in the question styles. Each question should be significantly different in logic, structure, or scenario.\n"
        "Use a mix of data structures (e.g., arrays, strings, trees, graphs), problem types (e.g., simulation, greedy, dynamic programming), and input/output styles.\n\n"
        "Each question must be a JSON object with the following keys:\n"
        '- "title": string (concise and descriptive)\n'
        '- "description": string (clearly describes the problem statement)\n'
        '- "companies_asked": list of strings (company names; vary across questions)\n'
        '- "year_asked": integer or null (use realistic years like 2018–2024)\n'
        '- "explanation": string (include logic, edge case discussion, and example walkthroughs)\n'
        '- "constraints": string (specify time/space/input constraints if relevant)\n'
        '- "sample_io": list of 3 objects, each with "input" and "output" keys as strings\n'
        '- "test_cases": list of 4 or more objects, each with the following keys:\n'
        '    - "input": string (stdin input)\n'
        '    - "expected_output": string (stdout output)\n'
        '    - "is_sample": boolean (true if shown to user)\n'
        '    - "test_type": one of ["normal", "edge", "boundary"]\n\n'
        "Return a JSON array containing exactly 5 such question objects.\n\n"
        "**Important:**\n"
        "- Respond ONLY with the JSON array.\n"
        "- Do NOT include any markdown formatting, explanation text, or comments.\n"
        '- Ensure all property names and string values use double quotes.\n'
        "- The JSON must be valid and parseable.\n"
        "- Each question must be different in structure and behavior.\n"
        "- Vary the companies_asked, year_asked, and question intent.\n"
        "- Ensure every question has at least one edge case and one boundary test case.\n\n"
        "Example output:\n\n"
        "[\n"
        "  {\n"
        '    \"title\": \"Example Question Title\",\n'
        '    \"description\": \"Detailed question description here...\",\n'
        '    \"companies_asked\": [\"Google\", \"Amazon\"],\n'
        '    \"year_asked\": 2023,\n'
        '    \"explanation\": \"Explanation with examples...\",\n'
        '    \"constraints\": \"1 <= N <= 10^5, O(N log N) expected\",\n'
        '    \"sample_io\": [\n'
        '      {\"input\": \"1 2\", \"output\": \"3\"},\n'
        '      {\"input\": \"4 5\", \"output\": \"9\"},\n'
        '      {\"input\": \"7 8\", \"output\": \"15\"}\n'
        '    ],\n'
        '    \"test_cases\": [\n'
        '      {\"input\": \"1 2\", \"expected_output\": \"3\", \"is_sample\": true, \"test_type\": \"normal\"},\n'
        '      {\"input\": \"0\\n\", \"expected_output\": \"0\", \"is_sample\": false, \"test_type\": \"edge\"},\n'
        '      {\"input\": \"1\\n999\", \"expected_output\": \"999\", \"is_sample\": false, \"test_type\": \"edge\"},\n'
        '      {\"input\": \"100000\\n1 1 1 ...\", \"expected_output\": \"100000\", \"is_sample\": false, \"test_type\": \"boundary\"}\n'
        '    ]\n'
        "  },\n"
        "  ...\n"
        "]"
    )
