import json
import re
import time
from pathlib import Path

from src.llm import LLMClient, load_community
from src.memory import get_conversation_context

CONFIG_DIR = Path(__file__).parent.parent / "config"


def _is_question(text: str) -> bool:
    """Detecta si un mensaje es una pregunta o petición de ayuda."""
    text_lower = text.lower()
    # Signos de interrogación
    if "?" in text:
        return True
    # Palabras clave de preguntas/ayuda en español
    keywords = [
        "alguien sabe", "alguien puede", "cómo puedo", "como puedo",
        "dónde está", "donde esta", "donde están", "dónde encuentro",
        "no puedo acceder", "no me deja", "no funciona", "no me aparece",
        "no encuentro", "no me sale", "tengo un problema", "tengo una duda",
        "ayuda", "help", "me podéis", "me pueden", "me puedes",
        "sabéis", "sabeis", "saben", "alguien", "por favor",
        "cuándo", "cuando es", "a qué hora", "a que hora",
        "qué paso", "que paso", "qué pasa", "que pasa",
        "cómo se", "como se", "necesito", "me gustaría saber",
    ]
    return any(kw in text_lower for kw in keywords)


class ResponseRouter:
    def __init__(self, llm: LLMClient, bot_user_id: str, owner_id: str):
        self.llm = llm
        self.bot_user_id = bot_user_id
        self.owner_id = owner_id
        # Rate limiting: {server_id: [timestamps]}
        self._rate_limits: dict[str, list[float]] = {}
        self._cooldowns: dict[str, float] = {}  # {channel_id: last_response_time}

    def _is_rate_limited(self, server_id: str, max_per_day: int) -> bool:
        """Verifica si se ha excedido el límite de mensajes por día."""
        now = time.time()
        day_ago = now - 86400

        if server_id not in self._rate_limits:
            self._rate_limits[server_id] = []

        self._rate_limits[server_id] = [
            t for t in self._rate_limits[server_id] if t > day_ago
        ]

        return len(self._rate_limits[server_id]) >= max_per_day

    def _is_on_cooldown(self, channel_id: str, cooldown_seconds: int) -> bool:
        """Verifica si el canal está en cooldown."""
        if channel_id not in self._cooldowns:
            return False
        return (time.time() - self._cooldowns[channel_id]) < cooldown_seconds

    def _record_response(self, server_id: str, channel_id: str):
        """Registra que se envió una respuesta (para rate limiting)."""
        now = time.time()
        if server_id not in self._rate_limits:
            self._rate_limits[server_id] = []
        self._rate_limits[server_id].append(now)
        self._cooldowns[channel_id] = now

    async def should_respond(
        self,
        message_content: str,
        server_id: str,
        channel_id: str,
        user_id: str,
        mentions_bot: bool,
        is_reply_to_bot: bool,
        rate_limit_per_day: int = 15,
    ) -> dict:
        """Decide si el bot debe responder a un mensaje."""
        # Nunca responder a sí mismo
        if user_id == self.bot_user_id:
            return {"respond": False, "reason": "propio_mensaje"}

        # Siempre responder al owner (sin necesidad de mención)
        if user_id == self.owner_id:
            return {"respond": True, "reason": "owner"}

        # Cargar config de la comunidad
        community = load_community(server_id)

        if not community:
            return {"respond": False, "reason": "servidor_no_configurado"}

        # Verificar si el canal está en la lista de activos
        canales_activos = {
            c["channel_id"] for c in community.get("canales_activos", [])
        }
        canales_ignorados = set(community.get("canales_ignorados", []))

        if channel_id in canales_ignorados:
            return {"respond": False, "reason": "canal_ignorado"}

        if canales_activos and channel_id not in canales_activos:
            return {"respond": False, "reason": "canal_no_activo"}

        reglas = community.get("reglas_respuesta", {})

        # Si lo mencionan directamente, siempre responder
        if mentions_bot and reglas.get("responder_si_mencionado", True):
            return {"respond": True, "reason": "mencion_directa"}

        # Si es reply a un mensaje del bot
        if is_reply_to_bot:
            return {"respond": True, "reason": "reply_al_bot"}

        # Rate limiting (por día)
        if self._is_rate_limited(server_id, rate_limit_per_day):
            return {"respond": False, "reason": "rate_limited"}

        # Cooldown por canal
        cooldown = reglas.get("cooldown_segundos", 30)
        if self._is_on_cooldown(channel_id, cooldown):
            return {"respond": False, "reason": "cooldown"}

        # Si es una pregunta directa o petición de ayuda, responder SIN consultar Haiku
        if _is_question(message_content):
            return {"respond": True, "reason": "pregunta_detectada"}

        # Para otros mensajes, usar Haiku para decidir
        if reglas.get("responder_si_tema_relevante", True):
            recent = await get_conversation_context(channel_id, minutes=10)
            context_str = "\n".join(
                f"[{m['username']}]: {m['content']}" for m in recent[-10:]
            )

            decision = await self.llm.should_respond(
                message_content, context_str, community
            )

            if decision.get("respond"):
                return {
                    "respond": True,
                    "reason": f"llm_decision: {decision.get('reason', '')}",
                }

        return {"respond": False, "reason": "no_relevante"}

    def record_response(self, server_id: str, channel_id: str):
        """Registra una respuesta enviada para rate limiting."""
        self._record_response(server_id, channel_id)
