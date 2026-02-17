import aiosqlite
import json
import time
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data" / "db" / "memory.db"


async def init_db():
    """Inicializa la base de datos con las tablas necesarias."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                discord_message_id TEXT UNIQUE,
                server_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                content TEXT NOT NULL,
                is_bot_response INTEGER DEFAULT 0,
                reply_to_message_id TEXT,
                timestamp REAL NOT NULL,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            );

            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                display_name TEXT,
                servers TEXT DEFAULT '[]',
                interaction_count INTEGER DEFAULT 0,
                last_interaction REAL,
                personality_notes TEXT DEFAULT '',
                created_at REAL DEFAULT (strftime('%s', 'now'))
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                server_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                last_activity REAL NOT NULL,
                message_count INTEGER DEFAULT 0,
                participants TEXT DEFAULT '[]',
                topic TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_messages_channel
                ON messages(channel_id, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_user
                ON messages(user_id, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_messages_server
                ON messages(server_id, timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_conversations_channel
                ON conversations(channel_id, last_activity DESC);

            CREATE TABLE IF NOT EXISTS learned_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trigger_content TEXT NOT NULL,
                response_content TEXT NOT NULL,
                server_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                positive_reactions INTEGER DEFAULT 0,
                negative_reactions INTEGER DEFAULT 0,
                quality_score REAL DEFAULT 0.5,
                created_at REAL DEFAULT (strftime('%s', 'now'))
            );

            CREATE TABLE IF NOT EXISTS user_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                topic TEXT NOT NULL,
                frequency INTEGER DEFAULT 1,
                last_seen REAL,
                UNIQUE(user_id, topic)
            );

            CREATE INDEX IF NOT EXISTS idx_learned_quality
                ON learned_responses(quality_score DESC);
            CREATE INDEX IF NOT EXISTS idx_user_topics
                ON user_topics(user_id, frequency DESC);
        """)
        await db.commit()


async def save_message(
    discord_message_id: str,
    server_id: str,
    channel_id: str,
    user_id: str,
    username: str,
    content: str,
    is_bot_response: bool = False,
    reply_to_message_id: str | None = None,
):
    """Guarda un mensaje en la base de datos."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR IGNORE INTO messages
            (discord_message_id, server_id, channel_id, user_id, username, content,
             is_bot_response, reply_to_message_id, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                discord_message_id,
                server_id,
                channel_id,
                user_id,
                username,
                content,
                int(is_bot_response),
                reply_to_message_id,
                time.time(),
            ),
        )
        await db.commit()


async def get_recent_messages(channel_id: str, limit: int = 20) -> list[dict]:
    """Obtiene los mensajes más recientes de un canal."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM messages
            WHERE channel_id = ?
            ORDER BY timestamp DESC
            LIMIT ?""",
            (channel_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]


async def get_user_history(user_id: str, limit: int = 10) -> list[dict]:
    """Obtiene el historial de mensajes de un usuario."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM messages
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?""",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in reversed(rows)]


async def update_user(user_id: str, username: str, server_id: str):
    """Actualiza o crea un perfil de usuario."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Verificar si existe
        cursor = await db.execute(
            "SELECT servers, interaction_count FROM users WHERE user_id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()

        if row:
            servers = json.loads(row[0])
            if server_id not in servers:
                servers.append(server_id)
            await db.execute(
                """UPDATE users SET
                    username = ?,
                    servers = ?,
                    interaction_count = interaction_count + 1,
                    last_interaction = ?
                WHERE user_id = ?""",
                (username, json.dumps(servers), time.time(), user_id),
            )
        else:
            await db.execute(
                """INSERT INTO users (user_id, username, servers, interaction_count, last_interaction)
                VALUES (?, ?, ?, 1, ?)""",
                (user_id, username, json.dumps([server_id]), time.time()),
            )
        await db.commit()


async def get_user_profile(user_id: str) -> dict | None:
    """Obtiene el perfil de un usuario."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        return dict(row) if row else None


async def search_messages(
    server_id: str, query: str, limit: int = 10
) -> list[dict]:
    """Busca mensajes por contenido en un servidor."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM messages
            WHERE server_id = ? AND content LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?""",
            (server_id, f"%{query}%", limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_conversation_context(
    channel_id: str, minutes: int = 30
) -> list[dict]:
    """Obtiene mensajes recientes dentro de una ventana de tiempo."""
    cutoff = time.time() - (minutes * 60)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT * FROM messages
            WHERE channel_id = ? AND timestamp > ?
            ORDER BY timestamp ASC""",
            (channel_id, cutoff),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


# --- SISTEMA DE APRENDIZAJE ---


async def save_learned_response(
    trigger: str, response: str, server_id: str, channel_id: str
):
    """Guarda una respuesta del bot para aprender de ella."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO learned_responses
            (trigger_content, response_content, server_id, channel_id)
            VALUES (?, ?, ?, ?)""",
            (trigger, response, server_id, channel_id),
        )
        await db.commit()


async def update_response_reaction(
    bot_message_id: str, is_positive: bool
):
    """Actualiza el score de una respuesta basado en reacciones."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Buscar la respuesta del bot
        cursor = await db.execute(
            "SELECT content FROM messages WHERE discord_message_id = ? AND is_bot_response = 1",
            (bot_message_id,),
        )
        row = await cursor.fetchone()
        if not row:
            return

        content = row[0]
        if is_positive:
            await db.execute(
                """UPDATE learned_responses SET
                    positive_reactions = positive_reactions + 1,
                    quality_score = MIN(1.0, quality_score + 0.1)
                WHERE response_content = ?""",
                (content,),
            )
        else:
            await db.execute(
                """UPDATE learned_responses SET
                    negative_reactions = negative_reactions + 1,
                    quality_score = MAX(0.0, quality_score - 0.15)
                WHERE response_content = ?""",
                (content,),
            )
        await db.commit()


async def get_good_responses(server_id: str, limit: int = 5) -> list[dict]:
    """Obtiene las mejores respuestas pasadas para few-shot learning."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT trigger_content, response_content, quality_score
            FROM learned_responses
            WHERE server_id = ? AND quality_score >= 0.6
            ORDER BY quality_score DESC, positive_reactions DESC
            LIMIT ?""",
            (server_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def track_user_topic(user_id: str, username: str, topic: str):
    """Registra un tema de interés de un usuario."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT INTO user_topics (user_id, username, topic, last_seen)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, topic) DO UPDATE SET
                frequency = frequency + 1,
                last_seen = ?""",
            (user_id, username, topic, time.time(), time.time()),
        )
        await db.commit()


async def get_user_topics(user_id: str, limit: int = 5) -> list[dict]:
    """Obtiene los temas más frecuentes de un usuario."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            """SELECT topic, frequency FROM user_topics
            WHERE user_id = ?
            ORDER BY frequency DESC
            LIMIT ?""",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]


async def get_user_interaction_summary(user_id: str) -> dict:
    """Genera un resumen de las interacciones con un usuario."""
    async with aiosqlite.connect(DB_PATH) as db:
        # Total de mensajes
        cursor = await db.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
        )
        total = (await cursor.fetchone())[0]

        # Último mensaje
        cursor = await db.execute(
            "SELECT content, timestamp FROM messages WHERE user_id = ? ORDER BY timestamp DESC LIMIT 1",
            (user_id,),
        )
        last = await cursor.fetchone()

        # Interacciones con el bot
        cursor = await db.execute(
            """SELECT COUNT(*) FROM messages m1
            INNER JOIN messages m2 ON m1.reply_to_message_id = m2.discord_message_id
            WHERE m2.user_id = ? AND m1.is_bot_response = 1""",
            (user_id,),
        )
        bot_interactions = (await cursor.fetchone())[0]

        # Temas
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT topic, frequency FROM user_topics WHERE user_id = ? ORDER BY frequency DESC LIMIT 3",
            (user_id,),
        )
        topics = [dict(r) for r in await cursor.fetchall()]

    return {
        "total_messages": total,
        "last_message": last[0] if last else None,
        "last_seen": last[1] if last else None,
        "bot_interactions": bot_interactions,
        "top_topics": topics,
    }
