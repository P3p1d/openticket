import os
import gettext
from fastapi import Request

LOCALES_DIR = os.path.join(os.path.dirname(__file__), "locales")

def get_translator(request: Request):
    # Detect language from query param first, then Accept-Language header
    lang = request.query_params.get("lang")
    if not lang:
        accept_lang = request.headers.get("Accept-Language", "")
        if "cs" in accept_lang.lower():
            lang = "cs"
        else:
            lang = "en"
            
    try:
        translation = gettext.translation("messages", localedir=LOCALES_DIR, languages=[lang])
        return translation.gettext
    except FileNotFoundError:
        return gettext.gettext

def inject_translator(request: Request):
    request.state.gettext = get_translator(request)
