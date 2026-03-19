# # llm_utils.py

def clean_generated_content(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        first_line_end = content.find("\n")
        if first_line_end != -1:
            content = content[first_line_end:].lstrip("\r\n")
    if content.endswith("```"):
        last_line_start = content.rfind("\n```")
        if last_line_start != -1:
            content = content[:last_line_start].rstrip("\r\n")
    if content.lower().startswith("json"):
        content = content[4:].lstrip("\r\n")
    return content.strip()
