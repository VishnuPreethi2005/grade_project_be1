"""
run_code.py

This module provides an API endpoint to compile and execute code in multiple languages
(Python, C, C++, Java), evaluate it against provided test cases, and return execution
results or compilation errors with line numbers.
"""

import os
import uuid
import subprocess
import re
import logging
from rest_framework.response import Response
from rest_framework.decorators import api_view

logger = logging.getLogger(__name__)

LANGUAGES = {
    'python': '.py',
    'c': '.c',
    'cpp': '.cpp',
    'java': '.java',
}


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


def run_code_logic(data: dict) -> dict:
    code = data.get('code')
    language = data.get('language')
    testcases = data.get('testcases', [])

    logger.info("Code execution request received.")
    logger.info("Language: %s", language)
    if code:
        logger.debug("Code preview:\n%s...", code[:100])
    else:
        logger.error("No code provided.")

    if not code or not language:
        return {'error': 'Code and language are required.', 'status_code': 400}

    if language not in LANGUAGES:
        return {'error': 'Unsupported language', 'status_code': 400}

    is_run_mode = not testcases
    if is_run_mode:
        test_input = data.get('input', '')
        testcases = [{'input': test_input, 'expected_output': ''}]

    ext = LANGUAGES[language]
    folder = 'temp_codes'
    os.makedirs(folder, exist_ok=True)
    results = []

    for case in testcases:
        test_input = case['input']
        expected_output = case.get('expected_output', '').strip()
        output_exe = None

        # Prepare code based on language
        if language == 'python':
            temp_code = inject_input_wrapper_python(code, test_input)
        else:
            temp_code = code

        # Filename handling
        if language == 'java':
            match = re.search(r'public\s+class\s+(\w+)', code)
            if not match:
                return {'error': 'No public class found in Java code', 'status_code': 400}
            class_name = match.group(1)
            filename = f"{class_name}.java"
        else:
            filename = f'code_{uuid.uuid4().hex}{ext}'

        filepath = os.path.join(folder, filename)

        try:
            # Write to temp file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(temp_code)

            # Compile and prepare command
            if language == 'python':
                cmd = ['python', filepath]
                run_kwargs = {'input': None}
            elif language == 'c':
                output_exe = os.path.join(folder, f'{uuid.uuid4().hex}')
                subprocess.run(['gcc', filepath, '-o', output_exe], check=True, stderr=subprocess.PIPE, text=True)
                cmd = [output_exe]
                run_kwargs = {'input': test_input}
            elif language == 'cpp':
                output_exe = os.path.join(folder, f'{uuid.uuid4().hex}')
                subprocess.run(['g++', filepath, '-o', output_exe], check=True, stderr=subprocess.PIPE, text=True)
                cmd = [output_exe]
                run_kwargs = {'input': test_input}
            elif language == 'java':
                java_folder = os.path.abspath(folder)
                subprocess.run(['javac', filename], cwd=java_folder, check=True, stderr=subprocess.PIPE, text=True)
                class_name = os.path.splitext(os.path.basename(filepath))[0]
                cmd = ['java', '-cp', java_folder, class_name]
                run_kwargs = {'input': test_input}

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5, **run_kwargs)

            # Python-specific runtime error handling
            if language == 'python' and "Traceback" in result.stderr:
                stderr = result.stderr
                match = re.search(r'File ".*?", line (\d+)', stderr)
                error_line = int(match.group(1)) if match else None
                return {
                    'stdout': result.stdout.strip(),
                    'stderr': stderr,
                    'error_line': error_line,
                    'status_code': 400
                }

            actual_output = result.stdout.strip()
            passed = actual_output == expected_output if not is_run_mode else True

            results.append({
                'input': test_input,
                'expected_output': expected_output,
                'output': actual_output,
                'passed': passed
            })

        except subprocess.CalledProcessError as e:
            stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else e.stderr or ""
            stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else e.stdout or ""
            error_line = None

            if language == 'python':
                match = re.search(r'File ".*?", line (\d+)', stderr)
                if match:
                    error_line = int(match.group(1))
                return {
                    'stdout': stdout.strip(),
                    'stderr': 'Syntax Error Detected:\n' + stderr,
                    'error_line': error_line,
                    'status_code': 400
                }

            elif language in ['c', 'cpp']:
                error_line, adjusted_stderr = adjust_cpp_error_line_numbers(stderr)
                return {
                    'stdout': stdout.strip(),
                    'stderr': 'Compilation Error:\n' + adjusted_stderr,
                    'error_line': error_line,
                    'status_code': 400
                }

            elif language == 'java':
                match = re.search(r'\.java:(\d+): error:', stderr)
                if match:
                    error_line = int(match.group(1))
                return {
                    'stdout': stdout.strip(),
                    'stderr': 'Compilation Error:\n' + stderr,
                    'error_line': error_line,
                    'status_code': 400
                }

        except subprocess.TimeoutExpired:
            return {
                'stdout': '',
                'stderr': 'Execution timed out',
                'status_code': 400
            }

        finally:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                if output_exe and os.path.exists(output_exe):
                    os.remove(output_exe)
                if language == 'java':
                    class_file = os.path.join(folder, f"{os.path.splitext(filename)[0]}.class")
                    if os.path.exists(class_file):
                        os.remove(class_file)
            except Exception as cleanup_error:
                logger.warning("Cleanup failed: %s", cleanup_error)

    # Return for simple "Run" mode
    if is_run_mode and results:
        return {
            'stdout': results[0].get('output', ''),
            'stderr': '',
            'error_line': None,
            'status_code': 200
        }

    # Return test mode result
    passed_count = sum(1 for r in results if r.get('passed'))
    score = round((passed_count / len(results)) * 10, 2) if results else 0

    return {
        'score': score,
        'results': results,
        'status_code': 200
    }




def inject_input_wrapper_python(code: str, test_input: str) -> str:
    # Handle empty input better
    input_lines = test_input.strip().splitlines() if test_input.strip() else [""]
    
    wrapper = f"""
inputs = {repr(input_lines)}
input_index = 0
def input():
    global input_index
    if input_index >= len(inputs):
        # More graceful handling
        return ""  # or raise a more descriptive error
    val = inputs[input_index]
    input_index += 1
    return val
"""
    return wrapper.strip() + "\n\n" + code


def adjust_cpp_error_line_numbers(stderr: str, line_offset: int = 0):
    """
    Adjusts error line numbers in C/C++ compiler error messages.
    """
    adjusted_lines = []
    error_line = None
    pattern = re.compile(r'^(.*?):(\d+):(\d+):\s*(error|warning):\s*(.*)$')

    for line in stderr.splitlines():
        match = pattern.match(line)
        if match:
            file_path, line_no, col_no, level, message = match.groups()
            adjusted_line_no = max(1, int(line_no) - line_offset)
            adjusted_line = f"{file_path}:{adjusted_line_no}:{col_no}: {level}: {message}"
            adjusted_lines.append(adjusted_line)
            if level == "error" and error_line is None:
                error_line = adjusted_line_no
        else:
            adjusted_lines.append(line)

    return error_line, "\n".join(adjusted_lines)
