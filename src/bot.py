import logging

import discord

from src.filter import filter_response
from src.llm import LLMClient
from src.memory import (
    get_recent_messages,
    get_user_interaction_summary,
    get_user_topics,
    init_db,
    save_learned_response,
    save_message,
    track_user_topic,
    update_response_reaction,
    update_user,
)
from src.router import ResponseRouter

logger = logging.getLogger("discord_agent")

# Reacciones positivas y negativas
POSITIVE_REACTIONS = {"👍", "❤️", "🔥", "✅", "💯", "🙌", "👏", "😊", "🎯", "⭐"}
NEGATIVE_REACTIONS = {"👎", "❌", "😕", "🤔"}

# Keywords para detectar temas
TOPIC_KEYWORDS = {
    "neo": "NEO Software",
    "formación": "formación",
    "formacion": "formación",
    "bloque": "bloques formativos",
    "directo": "directos/eventos",
    "zoom": "directos/eventos",
    "creator talk": "Creator Talks",
    "reel": "contenido/reels",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "nicho": "nicho/marca personal",
    "marca personal": "nicho/marca personal",
    "contenido": "creación de contenido",
    "suscripción": "suscripción NEO",
    "suscripcion": "suscripción NEO",
    "cancelar": "cancelar suscripción",
    "acceso": "acceso plataforma",
    "grabación": "grabaciones",
    "grabacion": "grabaciones",
    "ticket": "soporte técnico",
    "notion": "Notion",
    "venta": "ventas/cierre",
    "cliente": "clientes",
}


def detect_topics(text: str) -> list[str]:
    """Detecta temas en un mensaje."""
    text_lower = text.lower()
    found = set()
    for keyword, topic in TOPIC_KEYWORDS.items():
        if keyword in text_lower:
            found.add(topic)
    return list(found)


class AgentBot(discord.Client):
    def __init__(self, llm: LLMClient, owner_id: str, rate_limit: int = 15):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.reactions = True
        super().__init__(intents=intents)

        self.llm = llm
        self.owner_id = owner_id
        self.rate_limit = rate_limit
        self.router: ResponseRouter | None = None

    async def on_ready(self):
        logger.info(f"Bot conectado como {self.user} (ID: {self.user.id})")
        logger.info(f"Servidores: {[g.name for g in self.guilds]}")

        await init_db()

        self.router = ResponseRouter(
            llm=self.llm,
            bot_user_id=str(self.user.id),
            owner_id=self.owner_id,
        )

        logger.info("Bot listo y escuchando mensajes.")

    async def on_reaction_add(self, reaction: discord.Reaction, user: discord.User):
        """Aprende de las reacciones a los mensajes del bot."""
        # Solo nos interesan reacciones a mensajes del bot
        if reaction.message.author.id != self.user.id:
            return
        # Ignorar reacciones propias
        if user.bot:
            return

        emoji = str(reaction.emoji)
        is_positive = emoji in POSITIVE_REACTIONS
        is_negative = emoji in NEGATIVE_REACTIONS

        if is_positive or is_negative:
            await update_response_reaction(
                str(reaction.message.id), is_positive
            )
            logger.info(
                f"Reacción {'positiva' if is_positive else 'negativa'} "
                f"de {user.display_name}: {emoji} → mensaje: {reaction.message.content[:50]}"
            )

    async def on_message(self, message: discord.Message):
        if not message.guild:
            return

        if message.author.bot:
            return

        server_id = str(message.guild.id)
        channel_id = str(message.channel.id)
        user_id = str(message.author.id)
        username = message.author.display_name

        # Guardar mensaje
        reply_to_id = None
        if message.reference and message.reference.message_id:
            reply_to_id = str(message.reference.message_id)

        await save_message(
            discord_message_id=str(message.id),
            server_id=server_id,
            channel_id=channel_id,
            user_id=user_id,
            username=username,
            content=message.content,
            reply_to_message_id=reply_to_id,
        )

        # Actualizar perfil
        await update_user(user_id, username, server_id)

        # Detectar y guardar temas del usuario
        topics = detect_topics(message.content)
        for topic in topics:
            await track_user_topic(user_id, username, topic)

        # Decidir si responder
        mentions_bot = self.user in message.mentions

        is_reply_to_bot = False
        if message.reference and message.reference.message_id:
            try:
                ref_msg = await message.channel.fetch_message(
                    message.reference.message_id
                )
                is_reply_to_bot = ref_msg.author.id == self.user.id
            except discord.NotFound:
                pass

        decision = await self.router.should_respond(
            message_content=message.content,
            server_id=server_id,
            channel_id=channel_id,
            user_id=user_id,
            mentions_bot=mentions_bot,
            is_reply_to_bot=is_reply_to_bot,
            rate_limit_per_day=self.rate_limit,
        )

        logger.info(
            f"[{message.guild.name}/#{message.channel.name}] "
            f"{username}: {message.content[:80]} → {decision}"
        )

        if not decision["respond"]:
            return

        # Obtener contexto enriquecido
        recent_messages = await get_recent_messages(channel_id, limit=15)

        # Obtener info del usuario para personalizar
        user_summary = await get_user_interaction_summary(user_id)
        user_topics_list = await get_user_topics(user_id)

        # Construir contexto extra del usuario
        user_context = ""
        if user_summary["total_messages"] > 1:
            user_context = f"\n[CONTEXTO DEL USUARIO {username}]: "
            user_context += f"Ha enviado {user_summary['total_messages']} mensajes. "
            if user_summary["bot_interactions"] > 0:
                user_context += f"Has interactuado con él/ella {user_summary['bot_interactions']} veces antes. "
            if user_topics_list:
                topics_str = ", ".join(t["topic"] for t in user_topics_list)
                user_context += f"Sus temas habituales: {topics_str}. "
            user_context += "Responde teniendo en cuenta este historial."

        # Generar respuesta
        async with message.channel.typing():
            response = await self.llm.generate_response(
                messages=recent_messages,
                server_id=server_id,
                bot_user_id=str(self.user.id),
                user_context=user_context,
            )

        if not response:
            logger.debug("LLM decidió no responder ([NO_RESPOND])")
            return

        # Filtrar respuesta
        filtered = await filter_response(response, self.llm)
        if not filtered:
            logger.warning(f"Respuesta filtrada: {response[:100]}")
            return

        # Enviar
        try:
            sent = await message.reply(filtered, mention_author=False)

            # Guardar respuesta
            await save_message(
                discord_message_id=str(sent.id),
                server_id=server_id,
                channel_id=channel_id,
                user_id=str(self.user.id),
                username=self.user.display_name,
                content=filtered,
                is_bot_response=True,
                reply_to_message_id=str(message.id),
            )

            # Guardar para aprendizaje
            await save_learned_response(
                trigger=message.content,
                response=filtered,
                server_id=server_id,
                channel_id=channel_id,
            )

            self.router.record_response(server_id, channel_id)

            logger.info(
                f"[{message.guild.name}/#{message.channel.name}] "
                f"Respondió a {username}: {filtered[:80]}"
            )

        except discord.Forbidden:
            logger.error(f"Sin permisos en #{message.channel.name}")
        except discord.HTTPException as e:
            logger.error(f"Error al enviar: {e}")
