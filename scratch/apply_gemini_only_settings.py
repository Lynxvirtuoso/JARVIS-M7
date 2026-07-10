import sys
sys.path.append('.')
from core.database import db

settings = {
    'stt_mode': 'cloud_first',
    'stt_provider': 'gemini_stt',
    'stt_fallback_order': '["gemini_stt", "local_faster_whisper"]',
    'tts_provider': 'gemini_tts',
    'tts_fallback_order': '["gemini_tts", "windows_sapi"]',
    'intent_provider': 'gemini',
    'intent_fallback_order': '["gemini_intent"]',
    'openai_enabled': 'false',
    'openai_stt_enabled': 'false',
    'openai_tts_enabled': 'false',
    'openai_intent_enabled': 'false',
    'gemini_tts_model': 'gemini-2.5-flash-preview-tts',
    'gemini_tts_voice': 'Kore',
    'gemini_stt_model': 'gemini-2.5-flash',
}

with db.get_connection() as conn:
    c = conn.cursor()
    for k, v in settings.items():
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)', (k, v))
    conn.commit()

print('Gemini-only settings applied successfully.')
print('Active settings:')
with db.get_connection() as conn:
    c = conn.cursor()
    for k in settings.keys():
        c.execute('SELECT value FROM settings WHERE key=?', (k,))
        row = c.fetchone()
        val = row[0] if row else 'NOT SET'
        print(f'  {k} = {val}')
