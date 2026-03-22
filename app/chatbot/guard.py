"""
Prompt injection guard — rejects messages that attempt to manipulate the AI.
"""
import re

_INJECTION_PATTERNS = [
    r'ignore (previous|all|prior) instructions',
    r'disregard (your|the) (previous|system|initial)',
    r'you are now',
    r'new instructions',
    r'jailbreak',
    r'\bDAN\b',
    r'pretend (you are|to be)',
    r'act as (if you are|a)',
    r'forget (everything|your instructions)',
    r'override (your|the) (system|instructions)',
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]


def is_safe(text: str) -> bool:
    """Return True if the message passes all safety checks."""
    for pattern in _COMPILED:
        if pattern.search(text):
            return False
    return True
