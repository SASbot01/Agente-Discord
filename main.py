import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("discord_agent")

# Validar variables de entorno
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
OWNER_DISCORD_ID = os.getenv("OWNER_DISCORD_ID")
RATE_LIMIT = int(os.getenv("RATE_LIMIT_PER_DAY", "15"))

if not DISCORD_TOKEN:
    logger.error("Falta DISCORD_TOKEN en .env")
    sys.exit(1)

if not ANTHROPIC_API_KEY:
    logger.error("Falta ANTHROPIC_API_KEY en .env")
    sys.exit(1)

if not OWNER_DISCORD_ID:
    logger.error("Falta OWNER_DISCORD_ID en .env")
    sys.exit(1)


def main():
    from src.bot import AgentBot
    from src.llm import LLMClient

    logger.info("Iniciando agente de Discord...")

    llm = LLMClient(api_key=ANTHROPIC_API_KEY)
    bot = AgentBot(llm=llm, owner_id=OWNER_DISCORD_ID, rate_limit=RATE_LIMIT)

    logger.info("Conectando a Discord...")
    bot.run(DISCORD_TOKEN)


if __name__ == "__main__":
    main()
