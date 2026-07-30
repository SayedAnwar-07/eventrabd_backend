import uuid

def create_id(prefix="USR"):
    """
    Generates a unique ID with a prefix.
    Example: USR-3f92b1c8a9d44b0e9f6d3c92
    """
    return f"{prefix}-{uuid.uuid4().hex[:24]}"
