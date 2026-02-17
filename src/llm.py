import json
from pathlib import Path

import anthropic

CONFIG_DIR = Path(__file__).parent.parent / "config"


def load_personality() -> dict:
    """Carga el perfil de personalidad."""
    path = CONFIG_DIR / "personality.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_community(server_id: str) -> dict | None:
    """Carga la configuración de una comunidad por server_id."""
    communities_dir = CONFIG_DIR / "communities"
    for file in communities_dir.glob("*.json"):
        with open(file, encoding="utf-8") as f:
            data = json.load(f)
            if data.get("server_id") == server_id:
                return data
    return None


def build_system_prompt(community: dict | None, personality: dict) -> str:
    """Construye el system prompt combinando personalidad + comunidad."""
    parts = []

    # Personalidad base
    parts.append(f"""Eres {personality['nombre']}. {personality['descripcion']}

ESTILO DE COMUNICACIÓN:
- Tono: {personality['tono_general']}
- Idioma principal: {personality['idioma_principal']}
- Muletillas que usas: {', '.join(personality['muletillas'])}
- Emojis que usas: {' '.join(personality['emojis_favoritos'])}

COSAS QUE NUNCA DIRÍAS O HARÍAS:
{chr(10).join('- ' + x for x in personality['nunca_dirias'])}""")

    # Ejemplos few-shot
    if personality.get("ejemplos_respuestas"):
        parts.append("\nEJEMPLOS DE CÓMO RESPONDES:")
        for ej in personality["ejemplos_respuestas"]:
            parts.append(f"""
Contexto: {ej['contexto']}
Usuario dice: "{ej['mensaje_usuario']}"
Tú respondes: "{ej['tu_respuesta']}"
""")

    # Contexto de comunidad
    if community:
        parts.append(f"""
CONTEXTO DE ESTA COMUNIDAD:
- Servidor: {community['nombre']}
- Descripción: {community['descripcion']}
- Temas frecuentes: {', '.join(community.get('temas_frecuentes', []))}
""")
        if community.get("tono_especifico"):
            parts.append(f"- Tono en este servidor: {community['tono_especifico']}")
        if community.get("contexto_adicional"):
            parts.append(f"- Contexto extra: {community['contexto_adicional']}")

        # Miembros clave
        if community.get("miembros_clave"):
            parts.append("\nPERSONAS QUE DEBES RECONOCER:")
            for m in community["miembros_clave"]:
                parts.append(
                    f"- {m['nombre']} (relación: {m['relacion']}): {m.get('notas', '')}"
                )

    # Respuestas frecuentes predefinidas
    if community and community.get("respuestas_frecuentes"):
        parts.append("\nRESPUESTAS PREDEFINIDAS (usa estas cuando apliquen, son las respuestas oficiales):")
        for clave, respuesta in community["respuestas_frecuentes"].items():
            parts.append(f"- {clave}: {respuesta}")

    # Enlaces frecuentes
    if community and community.get("enlaces_frecuentes"):
        parts.append("\nENLACES OFICIALES (usa SOLO estos enlaces, nunca inventes URLs):")
        for nombre_enlace, url in community["enlaces_frecuentes"].items():
            parts.append(f"- {nombre_enlace}: {url}")

    # Patrones reales de comportamiento
    if personality.get("patrones_reales"):
        parts.append("\nPATRONES DE COMPORTAMIENTO REAL:")
        for patron, desc in personality["patrones_reales"].items():
            parts.append(f"- {patron}: {desc}")

    # Instrucciones generales
    parts.append("""
REGLAS IMPORTANTES:
1. Responde como lo haría la persona real. NO suenes como un asistente de IA.
2. Sé natural, usa el mismo largo de mensaje que usaría la persona. Alex suele responder en 1-3 líneas cortas.
3. Si no sabes algo, redirige a un ticket o di que lo consultas. NUNCA inventes información.
4. Mantén la coherencia con mensajes anteriores en la conversación.
5. NO uses frases como "¡Claro!", "¡Por supuesto!", "¡Excelente pregunta!" u otras frases típicas de IA.
6. Responde en español (el idioma de la comunidad).
7. Si la conversación no requiere tu input, NO respondas (devuelve exactamente "[NO_RESPOND]").
8. Mantén tus respuestas cortas y naturales como en un chat real de Discord.
9. Cuando haya una pregunta frecuente (acceso NEO, cancelar suscripción, ver grabaciones), usa las respuestas predefinidas.
10. NUNCA inventes URLs o enlaces. Solo usa los enlaces oficiales listados arriba.
11. Para problemas técnicos complejos, redirige a ticket o menciona a Mario Fueyo.
12. Puedes tener pequeños errores ortográficos naturales, como lo haría Alex realmente.""")

    return "\n".join(parts)


def format_conversation(messages: list[dict], bot_user_id: str) -> list[dict]:
    """Convierte mensajes del historial al formato de la API de Claude."""
    formatted = []
    for msg in messages:
        role = "assistant" if msg.get("is_bot_response") or msg.get("user_id") == bot_user_id else "user"
        name = msg.get("username", "usuario")
        content = f"[{name}]: {msg['content']}"
        # Agrupar mensajes consecutivos del mismo rol
        if formatted and formatted[-1]["role"] == role:
            formatted[-1]["content"] += f"\n{content}"
        else:
            formatted.append({"role": role, "content": content})

    # La API requiere que el primer mensaje sea del usuario
    if formatted and formatted[0]["role"] == "assistant":
        formatted.pop(0)

    # La API requiere que el último mensaje sea del usuario
    if formatted and formatted[-1]["role"] == "assistant":
        formatted.append({"role": "user", "content": "[sistema]: continúa la conversación si es apropiado"})

    return formatted


class LLMClient:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.personality = load_personality()

    async def generate_response(
        self,
        messages: list[dict],
        server_id: str,
        bot_user_id: str,
        user_context: str = "",
        max_tokens: int = 500,
    ) -> str | None:
        """Genera una respuesta usando Claude Sonnet."""
        from src.memory import get_good_responses

        community = load_community(server_id)
        system_prompt = build_system_prompt(community, self.personality)

        # Añadir respuestas aprendidas con buena calidad
        good_responses = await get_good_responses(server_id, limit=3)
        if good_responses:
            system_prompt += "\n\nRESPUESTAS PASADAS QUE FUNCIONARON BIEN (usa como referencia de tono y estilo):"
            for gr in good_responses:
                system_prompt += f"\nPregunta: \"{gr['trigger_content'][:100]}\"\nRespuesta: \"{gr['response_content'][:200]}\""

        # Añadir contexto del usuario
        if user_context:
            system_prompt += f"\n{user_context}"

        formatted = format_conversation(messages, bot_user_id)

        if not formatted:
            return None

        response = self.client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system_prompt,
            messages=formatted,
        )

        text = response.content[0].text.strip()

        if "[NO_RESPOND]" in text:
            return None

        return text

    async def should_respond(
        self,
        message_content: str,
        channel_context: str,
        community: dict | None,
    ) -> dict:
        """Usa Haiku para decidir rápidamente si responder."""
        community_name = community.get("nombre", "la comunidad") if community else "la comunidad"
        prompt = f"""{self.personality['nombre']} es el Community Manager de {community_name}. Decide si debe responder a este mensaje.

DEBE responder si:
- Es una pregunta directa (sobre la formación, directos, NEO, acceso, fechas, horarios)
- Alguien pide ayuda o tiene un problema
- Alguien saluda o se despide y nadie más ha respondido
- Alguien agradece algo que Alex hizo
- Es un tema de soporte técnico

NO debe responder si:
- Es una conversación entre otros miembros que no necesita su intervención
- Alguien solo comparte un enlace o recurso sin preguntar nada
- Ya respondió otro admin o miembro del equipo
- Es un mensaje muy corto sin contenido relevante (emoji suelto, "ok", etc.)

Contexto del canal (últimos mensajes):
{channel_context}

Mensaje nuevo: "{message_content}"

Responde SOLO con un JSON:
{{"respond": true/false, "reason": "razón breve", "urgency": "high/medium/low"}}"""

        response = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=100,
            messages=[{"role": "user", "content": prompt}],
        )

        text = response.content[0].text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Si no puede parsear, asumimos que no debe responder
            return {"respond": False, "reason": "parse_error", "urgency": "low"}

    async def check_quality(self, response: str) -> bool:
        """Usa Haiku para verificar que la respuesta suena natural."""
        prompt = f"""¿Esta respuesta suena como una persona real en Discord o como un asistente de IA?

Respuesta a evaluar: "{response}"

Responde SOLO "NATURAL" o "IA"."""

        result = self.client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=10,
            messages=[{"role": "user", "content": prompt}],
        )

        return "NATURAL" in result.content[0].text.upper()
