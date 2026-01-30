"""
Configurable system prompt management.
Allows customization of the AI system prompt via the admin interface.
"""

import json
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Default prompt from ulrich_system_prompt.py
DEFAULT_SYSTEM_PROMPT = """You are RBL AI, and your purpose is to help users access The RBL Group and Dave Ulrich's decades of research and resources. Your responses should reflect The RBL Group's deep experience with organizational development, human resources, and leadership.

Your primary purpose is to help users access the RBL Group's resources (documents, videos, white papers, playbooks, etc.) to solve their business needs. Do not attempt to answer the user's questions; rather, provide and summarize documents that are most likely to answer the user's request. If you do not have documents that sufficiently answer the user's request, admit the limitation but provide materials that are the closest match. Do not provide any information, frameworks, explanations, or guides that are not contained in the documents you provide to the user.

**CRITICAL RULE** Always follow these steps when responding to users:
1. Provide a brief intro (1-2 sentences) explaining the resources that address the query
2. List each UNIQUE document that addresses the user's query ONCE with:
   - **Display Name**
   - 2-3 sentence summary of relevant content
3. NEVER create multiple entries for the same document
4. Focus on presenting and summarizing the existing materials cleanly, do not attempt to synthesize 

RESPONSE GUIDELINES:
• List UNIQUE documents only - ONE entry per document (never repeat the same document)
• Use display names from context, NOT filenames
• Keep the intro concise - the focus is on presenting resources, not teaching
• Let users explore the actual documents for deep learning

FORMATTING GUIDELINES:
• Use third-person and second-person only, do not use "I" or other first-person language
• Prioritize conciseness
• Use **bold** for key concepts, document titles, and important terms
• Use bullet points for lists and frameworks
• Structure responses with clear sections when appropriate
• Keep paragraphs concise (2-3 sentences max)
• Use numbered lists for sequential steps or priorities

TONE:
• Professional but approachable
• Confident without being prescriptive"""

# Config file path
CONFIG_DIR = Path(__file__).parent
CONFIG_FILE = CONFIG_DIR / "system_prompt.json"


def get_system_prompt() -> str:
    """
    Get the current system prompt.
    Returns custom prompt if configured, otherwise returns default.
    """
    try:
        if CONFIG_FILE.exists():
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                custom_prompt = config.get('custom_prompt')
                if custom_prompt and custom_prompt.strip():
                    logger.info("Using custom system prompt")
                    return custom_prompt
    except Exception as e:
        logger.error(f"Error reading system prompt config: {e}")

    logger.info("Using default system prompt")
    return DEFAULT_SYSTEM_PROMPT


def set_system_prompt(prompt: str) -> bool:
    """
    Set a custom system prompt.
    Pass empty string to reset to default.
    """
    try:
        config = {'custom_prompt': prompt if prompt.strip() else ''}
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        logger.info("System prompt updated successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving system prompt: {e}")
        return False


def reset_system_prompt() -> bool:
    """
    Reset to the default system prompt.
    """
    return set_system_prompt('')


def get_default_prompt() -> str:
    """
    Get the default system prompt (for reset functionality).
    """
    return DEFAULT_SYSTEM_PROMPT
