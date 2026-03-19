from langchain_together import ChatTogether
import mlflow
import json
from pathlib import Path
from ..llm_base import GenerateResponse
from typing import List, Union

def calculate_cost(pricing_json_path, provider_key, model, prompt_tokens, completion_tokens):
    """
    Calculate the cost for LLM usage based on token counts and pricing data.
    
    Args:
        pricing_json_path: Path to the pricing JSON file
        provider_key: Provider name in the pricing JSON (e.g., "Mistral AI")
        model: Model name
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
    
    Returns:
        float: Total cost for the request
    """
    with open(pricing_json_path) as f:
        pricing = json.load(f)['pricing']
    input_cost = pricing[provider_key][model]['input']
    output_cost = pricing[provider_key][model]['output']
    total_cost = (prompt_tokens * input_cost / 1000) + (completion_tokens * output_cost / 1000)
    return total_cost

# def log_mlflow_metrics(
#     model: str,
#     temperature: float,
#     max_tokens: int,
#     prompt_tokens: int,
#     completion_tokens: int,
#     total_tokens: int,
#     cost: float,
#     prompt: str,
#     response: str = None,
#     batch_size: int = None,
#     # Add new parameters for logging
#     top_p: float = None,
#     top_k: int = None,
#     repetition_penalty: float = None,
#     stream_tokens: bool = None,
#     safety_model: str = None,
#     n: int = None,
#     stop: Union[str, List[str]] = None
# ):
#     """
#     Log metrics to MLflow for LLM requests with all Mistral parameters
#     """
#     import mlflow
#     with mlflow.start_run(nested=True,run_name=f"{model}_generate"):
#         params = {
#             "model": model,
#             "temperature": temperature,
#             "max_tokens": max_tokens
#         }
        
#         # Add new parameters if provided
#         if top_p is not None:
#             params["top_p"] = top_p
#         if top_k is not None:
#             params["top_k"] = top_k
#         if repetition_penalty is not None:
#             params["repetition_penalty"] = repetition_penalty
#         if stream_tokens is not None:
#             params["stream_tokens"] = stream_tokens
#         if safety_model is not None:
#             params["safety_model"] = safety_model
#         if n is not None:
#             params["n"] = n
#         if stop is not None:
#             params["stop"] = stop
#         if batch_size is not None:
#             params["batch_size"] = batch_size
            
#         mlflow.log_params(params)
        
#         metrics = {
#             "prompt_tokens": prompt_tokens,
#             "completion_tokens": completion_tokens,
#             "total_tokens": total_tokens,
#             "cost": cost
#         }
#         if batch_size is not None:
#             # For batch, log total tokens and cost as well
#             metrics["total_prompt_tokens"] = prompt_tokens
#             metrics["total_completion_tokens"] = completion_tokens
#             metrics["total_cost"] = cost
#         mlflow.log_metrics(metrics)
        
#         # Log text files
#         mlflow.log_text(prompt, "prompt.txt")
#         if response:
#             mlflow.log_text(response, "completion.txt")

async def together_generate_and_log(
    prompt,
    model,
    api_key,
    temperature,
    max_tokens,
    pricing_json_path,
    provider_key,
    user_params=None,
    # Add new parameters
    stop=None,
    top_p=0.7,
    top_k=50,
    repetition_penalty=1.0,
    stream_tokens=False,
    safety_model=None,
    n=1
):
    params = user_params or {}
    temp = params.get('temperature', temperature)
    max_tok = params.get('max_tokens', max_tokens)
    stop_param = params.get('stop', stop)
    top_p_param = params.get('top_p', top_p)
    top_k_param = params.get('top_k', top_k)
    repetition_penalty_param = params.get('repetition_penalty', repetition_penalty)
    stream_tokens_param = params.get('stream_tokens', stream_tokens)
    safety_model_param = params.get('safety_model', safety_model)
    n_param = params.get('n', n)
    
    # Build parameters for ChatTogether
    llm_params = {
        "model": model,
        "temperature": temp,
        "max_tokens": max_tok,
        "together_api_key": api_key
    }
    
    # Add optional parameters if they're not None/default
    if stop_param:
        llm_params["stop"] = stop_param
    if top_p_param != 1.0:
        llm_params["top_p"] = top_p_param
    if top_k_param != 50:
        llm_params["top_k"] = top_k_param
    if repetition_penalty_param != 1.0:
        llm_params["repetition_penalty"] = repetition_penalty_param
    if n_param != 1:
        llm_params["n"] = n_param
    
    llm = ChatTogether(**llm_params)
    response = await llm.ainvoke(prompt)
    usage = getattr(response, 'usage_metadata', None) or getattr(response, 'response_metadata', {}).get('token_usage', {})
    prompt_tokens = usage.get('input_tokens', usage.get('prompt_tokens', 0))
    completion_tokens = usage.get('output_tokens', usage.get('completion_tokens', 0))
    total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)
    
    # Calculate cost using the extracted function
    total_cost = calculate_cost(pricing_json_path, provider_key, model, prompt_tokens, completion_tokens)
    
    #Log to MLflow using the updated function with all parameters
    # log_mlflow_metrics(
    #     model=model,
    #     temperature=temp,
    #     max_tokens=max_tok,
    #     prompt_tokens=prompt_tokens,
    #     completion_tokens=completion_tokens,
    #     total_tokens=total_tokens,
    #     cost=total_cost,
    #     prompt=prompt,
    #     response=str(response),
    #     top_p=top_p_param,
    #     top_k=top_k_param,
    #     repetition_penalty=repetition_penalty_param,
    #     stream_tokens=stream_tokens_param,
    #     safety_model=safety_model_param,
    #     n=n_param,
    #     stop=stop_param
    # )
    
    return GenerateResponse(
        response=getattr(response, 'content', str(response)),
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cost=total_cost,
        model=model
    )

# --------- Batching support ---------
async def together_batch_generate_and_log(
    prompts: List[str],
    model,
    api_key,
    temperature,
    max_tokens,
    pricing_json_path,
    provider_key,
    user_params=None,
    # Add new parameters for batch processing
    stop=None,
    top_p=0.7,
    top_k=50,
    repetition_penalty=1.0,
    stream_tokens=False,
    safety_model=None,
    n=1
) -> List[GenerateResponse]:
    params = user_params or {}
    temp = params.get('temperature', temperature)
    max_tok = params.get('max_tokens', max_tokens)
    stop_param = params.get('stop', stop)
    top_p_param = params.get('top_p', top_p)
    top_k_param = params.get('top_k', top_k)
    repetition_penalty_param = params.get('repetition_penalty', repetition_penalty)
    stream_tokens_param = params.get('stream_tokens', stream_tokens)
    safety_model_param = params.get('safety_model', safety_model)
    n_param = params.get('n', n)
    
    # Build parameters for ChatTogether
    llm_params = {
        "model": model,
        "temperature": temp,
        "max_tokens": max_tok,
        "together_api_key": api_key
    }
    
    # Add optional parameters if they're not None/default
    if stop_param:
        llm_params["stop"] = stop_param
    if top_p_param != 1.0:
        llm_params["top_p"] = top_p_param
    if top_k_param != 50:
        llm_params["top_k"] = top_k_param
    if repetition_penalty_param != 1.0:
        llm_params["repetition_penalty"] = repetition_penalty_param
    if n_param != 1:
        llm_params["n"] = n_param
    
    llm = ChatTogether(**llm_params)
    responses = await llm.abatch(prompts)
    
    # Calculate total metrics for batch logging
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_cost = 0
    
    results = []
    for prompt, response in zip(prompts, responses):
        usage = getattr(response, 'usage_metadata', None) or getattr(response, 'response_metadata', {}).get('token_usage', {})
        prompt_tokens = usage.get('input_tokens', usage.get('prompt_tokens', 0))
        completion_tokens = usage.get('output_tokens', usage.get('completion_tokens', 0))
        total_tokens = usage.get('total_tokens', prompt_tokens + completion_tokens)
        
        # Calculate cost using the extracted function
        cost = calculate_cost(pricing_json_path, provider_key, model, prompt_tokens, completion_tokens)
        
        # Accumulate totals
        total_prompt_tokens += prompt_tokens
        total_completion_tokens += completion_tokens
        total_cost += cost
        
        results.append(GenerateResponse(
            response=getattr(response, 'content', str(response)),
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cost=cost,
            model=model
        ))
    
    # Log batch metrics using the separate function with all parameters
    # log_mlflow_metrics(
    #     model=model,
    #     temperature=temp,
    #     max_tokens=max_tok,
    #     prompt_tokens=total_prompt_tokens,
    #     completion_tokens=total_completion_tokens,
    #     total_tokens=total_prompt_tokens + total_completion_tokens,
    #     cost=total_cost,
    #     prompt=f"Batch of {len(prompts)} prompts",
    #     batch_size=len(prompts),
    #     top_p=top_p_param,
    #     top_k=top_k_param,
    #     repetition_penalty=repetition_penalty_param,
    #     stream_tokens=stream_tokens_param,
    #     safety_model=safety_model_param,
    #     n=n_param,
    #     stop=stop_param
    # )
    
    return results

# --------- SIMPLE GLOBAL ERROR HANDLER ---------
def handle_together_api_error(error: Exception, model: str) -> str:
    """
    Global error handler for all Together API LLMs.
    Returns user-friendly error message.
    """
    error_str = str(error).lower()
    
    if "401" in error_str and ("invalid api key" in error_str or "invalid_api_key" in error_str):
        return "Invalid API key provided: You can find your API key at https://api.together.xyz/settings/api-keys."
    elif "401" in error_str:
        return "Authentication Error: Invalid or missing API Key. Please verify your API credentials."
    elif "403" in error_str:
        return "Forbidden: Country, region, or territory not supported."
    elif "429" in error_str:
        return "Rate limit exceeded: Too many requests. Please slow down your request rate."
    elif "500" in error_str:
        return "Server Error: Issue on Together AI servers. Please retry after a brief wait."
    elif "503" in error_str:
        return "Service Overloaded: High traffic on servers. Please retry after a brief wait."
    else:
        return f"Together API Error: {str(error)}"
