"""
Specify the Parameters needed for Developer in backend
"""

# Specify method to use
LCEL_METHOD = "ainvoke"

# Add your model parameters here
model_dict = {
    "model": "gpt-4-1106-preview",
    "temperature": 0,
    "max_tokens": 200,
}

# Add input to prompts
input_dict = {
    "text": "hello",
    "source": "english",
    "destination": "french, tamil",
    "domain": "",
    "subdomain": "",
}
