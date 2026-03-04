import time
import tracemalloc
from functools import wraps
from typing import Callable, Any
from .logging import logger

def timeit(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        duration = time.perf_counter() - start
        logger.info(f"{func.__name__} executed in {duration:.4f}s")
        return result
    return wrapper

def memory_usage(func: Callable) -> Callable:
    @wraps(func)
    async def wrapper(*args, **kwargs) -> Any:
        tracemalloc.start()
        result = await func(*args, **kwargs)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        logger.info(f"Memory usage: Current: {current/1e6:.2f}MB, Peak: {peak/1e6:.2f}MB")
        return result
    return wrapper
