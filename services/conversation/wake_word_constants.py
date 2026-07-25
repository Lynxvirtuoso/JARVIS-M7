"""
services/conversation/wake_word_constants.py
Phase 1.5 Canonical Wake Word Constants & Variant Definitions for JARVIS M7.
Single source of truth for all wake phrases, phonetic mishear variants, and reject words.
"""

# Canonical wake phrases JARVIS accepts as definitive matches
WAKE_PHRASES = [
    "jarvis",
    "hey jarvis",
    "wake up jarvis",
    "hello jarvis",
]

# All accent / STT mishear variants — treated as exact matches when found in text.
# Expanding for Indian-English common mishearings: jollis, javish, jarvish, jar wish
FUZZY_VARIANTS = [
    # Single-word Jarvis variants
    "janus", "javis", "jarves", "charvis", "jaavas", "jarvez", "jarvas",
    "javish", "jarvish", "jollis", "jarviz", "jarfish", "jarvi",
    "jar vis", "jar fis", "jar face", "jar miss", "jar vice",
    # wake-up - variant
    "wake up janus", "wake up jervis", "wake up javis", "wake up javish",
    "wake up jarvish", "wake up jollis", "wake up jar wish",
    "wake up jarviz", "wake up jarves", "wake up jaarvis",
    "wake up service", "wake up jars", "wake up jealous",
    # hey - variant
    "hey janus", "hey jervis", "hey javis", "hey javish",
    "hey jarvish", "hey jollis", "hey jar wish",
    "hey jarviz", "hey charvis",
    # jar wish as two words
    "jar wish",
]

# Words that must NOT trigger wake even if they score high on fuzzy
REJECT_WORDS = {
    "hope", "yes", "jobless", "mewd", "okay", "no", "yeah",
    "welcome", "goodbye", "hello", "ciao", "mutual", "knowledge",
    "julius", "travis", "paris", "hollis",
}

# Fuzzy ratio threshold for full-phrase wake matching
WAKE_FUZZY_THRESHOLD = 0.80

# Fuzzy ratio threshold for single-word "is this a Jarvis-like word?" check
WAKE_WORD_FUZZY_THRESHOLD = 0.65

# Special action verbs required when 'service' mishear is used as prefix
SERVICE_ACTION_VERBS = {
    "open", "close", "start", "stop", "launch", "turn", "set", "play",
    "mute", "unmute", "volume", "status", "lock", "logout", "restart",
    "pause", "exit", "shutdown", "sleep", "standby", "search", "tell",
    "what", "which", "how", "when", "who", "delete", "create", "update"
}
