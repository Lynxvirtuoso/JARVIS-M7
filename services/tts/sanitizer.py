"""
services/tts/sanitizer.py
Text sanitizer for TTS audio synthesis.
Converts raw Markdown formatting, headers, links, and bullet points into natural spoken text.
Preserves original markdown formatting for HUD and history output.
"""
import re


def sanitize_for_tts(text: str) -> str:
    """
    Sanitize input text for speech synthesis while preserving readability.
    Strips raw Markdown markers (**bold**, *italics*, # headers, links, bullet points).
    """
    if not text:
        return ""

    sanitized = text

    # Remove code blocks or replace backticks with clean text
    sanitized = re.sub(r"```[a-zA-Z]*\n(.*?)```", r"\1", sanitized, flags=re.DOTALL)
    sanitized = re.sub(r"`([^`]+)`", r"\1", sanitized)

    # Convert Markdown headers (### Header -> Header.)
    sanitized = re.sub(r"^#{1,6}\s*(.+)$", r"\1.", sanitized, flags=re.MULTILINE)

    # Convert Markdown links [Link Text](http://...) -> Link Text
    sanitized = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", sanitized)

    # Remove bold and italic formatting (**text**, *text*, __text__, _text_)
    sanitized = re.sub(r"\*\*([^*]+)\*\*", r"\1", sanitized)
    sanitized = re.sub(r"\*([^*]+)\*", r"\1", sanitized)
    sanitized = re.sub(r"__([^_]+)__", r"\1", sanitized)
    sanitized = re.sub(r"_([^_]+)_", r"\1", sanitized)

    # Remove list bullet markers (- item, * item, 1. item)
    sanitized = re.sub(r"^\s*[-*+]\s+", "", sanitized, flags=re.MULTILINE)
    sanitized = re.sub(r"^\s*\d+\.\s+", "", sanitized, flags=re.MULTILINE)

    # Clean up multiple consecutive spaces or empty lines
    sanitized = re.sub(r"[ \t]+", " ", sanitized)
    sanitized = re.sub(r"\n\s*\n+", ". ", sanitized)
    sanitized = re.sub(r"\n", " ", sanitized)

    # Ensure punctuation spacing is natural
    sanitized = re.sub(r"\s+([.,?!:])", r"\1", sanitized)
    sanitized = re.sub(r"\.\.+", ".", sanitized)

    return sanitized.strip()
