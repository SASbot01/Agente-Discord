import re

from src.llm import LLMClient

# Frases típicas de IA que no queremos
AI_PHRASES = [
    "¡claro!",
    "¡por supuesto!",
    "¡excelente pregunta!",
    "como modelo de lenguaje",
    "como ia",
    "como asistente",
    "no puedo ayudarte con eso",
    "¡gran pregunta!",
    "absolutamente",
    "definitivamente puedo",
    "estaré encantado",
    "con mucho gusto",
    "¡hola! soy",
    "como inteligencia artificial",
]


def quick_filter(response: str) -> bool:
    """Filtro rápido basado en reglas para detectar respuestas tipo IA."""
    lower = response.lower()

    # Verificar frases de IA
    for phrase in AI_PHRASES:
        if phrase in lower:
            return False

    # Respuestas demasiado largas para Discord casual (más de 500 chars)
    if len(response) > 500:
        return False

    # Demasiados signos de exclamación (muy entusiasta = IA)
    if response.count("!") > 3:
        return False

    # Listas con viñetas (formato muy estructurado = IA)
    bullet_patterns = re.findall(r"^[\s]*[-•*]\s", response, re.MULTILINE)
    if len(bullet_patterns) > 2:
        return False

    return True


async def filter_response(response: str, llm: LLMClient) -> str | None:
    """Filtra la respuesta para asegurar calidad.

    Returns:
        La respuesta limpia si pasa el filtro, None si no.
    """
    # Filtro rápido primero
    if not quick_filter(response):
        # Intentar acortar/limpiar con LLM si es muy larga
        if len(response) > 500:
            # Truncar de forma natural
            sentences = re.split(r"[.!?]+", response)
            shortened = ""
            for s in sentences:
                if len(shortened) + len(s) < 300:
                    shortened += s + ". "
                else:
                    break
            response = shortened.strip()
            if not response:
                return None
        else:
            return None

    # Verificación con LLM (solo si el filtro rápido pasa)
    is_natural = await llm.check_quality(response)
    if not is_natural:
        return None

    return response
