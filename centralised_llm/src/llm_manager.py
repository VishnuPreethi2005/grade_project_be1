import json
import importlib
from dependency_injector import containers, providers
from pathlib import Path
from typing import Any
from .llm_base import GenerateRequest
from .utils.decorators import timeit, memory_usage


def load_llms_from_config(config_path):
    with open(config_path) as f:
        config = json.load(f)
    container = containers.DynamicContainer()
    for llm_name, llm_conf in config.items():
        module = importlib.import_module(llm_conf["module"])
        klass = getattr(module, llm_conf["class"])
        # Fetch only fixed parameters from config: class, module, api_key
        fixed_params = {k: v for k, v in llm_conf.items() if k in ("api_key",)}
        # Get default changeable parameters (everything except class, module, api_key)
        default_params = {k: v for k, v in llm_conf.items() if k not in ("class", "module", "api_key")}
        
        # Store both fixed and default parameters for later use
        container_data = {
            'class': klass,
            'fixed_params': fixed_params,
            'default_params': default_params
        }
        setattr(container, llm_name, container_data)
    return container

container = load_llms_from_config(str(Path(__file__).parent / 'config' / 'llm_config.json'))


def create_llm_instance(model_name: str, request_params: dict = None):
    """
    Create LLM instance with fixed parameters from config and changeable parameters from request.
    """
    if not hasattr(container, model_name):
        raise ValueError(f"Unknown model: {model_name}")
    
    container_data = getattr(container, model_name)
    klass = container_data['class']
    fixed_params = container_data['fixed_params']
    default_params = container_data['default_params'].copy()
    
    # Override default parameters with request parameters if provided
    if request_params:
        # Only allow changing parameters that are not fixed (class, module, api_key)
        allowed_params = {k: v for k, v in request_params.items() 
                         if k not in ("class", "module", "api_key")}
        default_params.update(allowed_params)
    
    # Combine fixed and changeable parameters
    all_params = {**fixed_params, **default_params}
    
    return klass(**all_params)


@timeit
@memory_usage
async def handle_request(json_input: str) -> Any:
    """
    Accepts either a single request (dict) or a batch (list of dicts).
    Decides automatically whether to use single or batch generation.
    Fixed parameters (class, module, api_key) are fetched from config.
    Other parameters can be overridden via 'parameters' in the request.
    """
    try:
        params = json.loads(json_input)
        
        # If it's a batch (list of dicts)
        if isinstance(params, list):
            if not params:
                return {"error": "Empty batch request"}
            
            model_name = params[0].get("model")
            if not hasattr(container, model_name):
                return {"error": f"Unknown model: {model_name}"}
            
            # Get request parameters from first item (assuming all items use same parameters)
            request_parameters = params[0].get("parameters", {})
            llm = create_llm_instance(model_name, request_parameters)
            
            # Create requests with parameters included
            requests = []
            for p in params:
                model = p["model"]
                prompt = p["prompt"]
                parameters = p.get("parameters", {})
                requests.append(GenerateRequest(model=model, prompt=prompt, parameters=parameters))
            
            responses = await llm.batch_generate(requests)
            return [resp.error if resp.error else resp.response for resp in responses]
        
        # If it's a single request (dict)
        else:
            model = params["model"]
            prompt = params["prompt"]
            request_parameters = params.get("parameters", {})
            
            if not hasattr(container, model):
                return {"error": f"Unknown model: {model}"}
            
            llm = create_llm_instance(model, request_parameters)
            request = GenerateRequest(model=model, prompt=prompt, parameters=request_parameters)
            response = await llm.generate(request)
            
            if response.error:
                return f"Error: {response.error}"
            else:
                return response.model_dump()
                
    except Exception as e:
        return {"error": str(e)}
