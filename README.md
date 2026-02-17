# Agente Discord — Creator Founder

Bot de Discord con IA que gestiona la comunidad **Creator Founder** respondiendo como **Alex Silvestre** (Community Manager). Usa Claude (Anthropic) como cerebro para generar respuestas naturales y aprende con cada interacción.

## Arquitectura

```
Mensaje en Discord
       ↓
   Bot (listener) → Guarda mensaje en SQLite + detecta temas del usuario
       ↓
   Router → ¿Debe responder?
       │
       ├── Mención directa / reply al bot → SÍ
       ├── Pregunta detectada (?, "alguien sabe", "no puedo acceder"...) → SÍ
       ├── Owner del bot → SÍ
       ├── Rate limit (15/día) o cooldown (2 min) → NO
       └── Otro mensaje → Haiku evalúa relevancia → SÍ/NO
       ↓
   LLM (Claude Sonnet) → Genera respuesta con:
       • System prompt personalizado (personalidad + comunidad)
       • Últimos 15 mensajes del canal
       • Perfil del usuario (temas, historial)
       • Respuestas pasadas que funcionaron bien
       ↓
   Filtro de calidad → ¿Suena natural o suena a IA?
       ↓
   Envía respuesta en Discord
```

## Stack

| Componente | Tecnología |
|---|---|
| Bot | discord.py |
| LLM (respuestas) | Claude Sonnet 4 |
| LLM (decisiones) | Claude Haiku 4.5 |
| Base de datos | SQLite (aiosqlite) |
| Config | JSON |

## Estructura del proyecto

```
agente discord/
├── main.py                    # Entry point
├── start.sh                   # Arrancar bot en background
├── stop.sh                    # Parar bot
├── requirements.txt
├── .env                       # Tokens (NO se sube a git)
├── .env.example               # Template de tokens
├── src/
│   ├── bot.py                 # Listener de Discord + sistema de aprendizaje
│   ├── router.py              # Decide si responder (reglas + Haiku)
│   ├── llm.py                 # Llamadas a Claude API + system prompts
│   ├── memory.py              # SQLite: mensajes, usuarios, aprendizaje
│   ├── filter.py              # Filtro anti-IA
│   └── trainer.py             # Importador de chats para entrenar personalidad
├── config/
│   ├── personality.json       # Personalidad del bot (tono, muletillas, ejemplos)
│   └── communities/
│       └── creator_founder.json  # Config del servidor (canales, miembros, respuestas)
└── data/
    ├── db/                    # Base de datos SQLite (se crea sola)
    └── training/              # JSONs exportados de Discord para entrenar
```

## Módulos

### `bot.py` — Listener principal
- Escucha todos los mensajes en los canales configurados
- Guarda cada mensaje en SQLite
- Detecta temas del usuario (NEO, formación, contenido, etc.)
- Trackea reacciones a los mensajes del bot para aprendizaje
- Coordina router → LLM → filtro → envío

### `router.py` — Motor de decisión
- **Responde siempre**: menciones, replies al bot, mensajes del owner, preguntas directas
- **Evalúa con Haiku**: mensajes ambiguos que no son claramente preguntas
- **No responde**: canales ignorados, rate limit alcanzado, cooldown activo, mensajes irrelevantes
- Rate limit: 15 mensajes/día por servidor
- Cooldown: 2 minutos entre respuestas por canal

### `llm.py` — Cerebro (Claude API)
- **Sonnet 4**: genera las respuestas con system prompt personalizado
- **Haiku 4.5**: decisiones rápidas (¿responder?) y filtro de calidad
- System prompt dinámico que combina: personalidad + comunidad + respuestas aprendidas + contexto del usuario
- Respuestas predefinidas para preguntas frecuentes (acceso NEO, cancelar suscripción, grabaciones)

### `memory.py` — Base de datos
- **messages**: todos los mensajes del servidor (historial completo)
- **users**: perfil de cada usuario (interacciones, servidores, notas)
- **learned_responses**: respuestas del bot con puntuación de calidad
- **user_topics**: temas de interés por usuario (frecuencia)

### `filter.py` — Filtro de calidad
- Detecta frases típicas de IA ("¡Claro!", "¡Excelente pregunta!", etc.)
- Rechaza respuestas demasiado largas (>500 chars)
- Rechaza respuestas con formato de IA (listas con viñetas, exceso de exclamaciones)
- Verificación final con Haiku: ¿suena natural o artificial?

### `trainer.py` — Entrenador de personalidad
- Procesa JSONs exportados de DiscordChatExporter
- Analiza estilo de escritura: emojis, muletillas, longitud, tono
- Genera automáticamente el `personality.json`

### `router.py` — Detección de preguntas
Detecta automáticamente preguntas por:
- Signos de interrogación (`?`)
- Palabras clave: "alguien sabe", "no puedo acceder", "dónde está", "ayuda", "necesito", etc.

## Sistema de aprendizaje

El bot mejora con cada interacción:

1. **Perfiles de usuario** — Detecta temas por keywords y guarda frecuencia. La próxima vez que ese usuario pregunte, el bot tiene contexto de sus intereses.

2. **Reacciones como feedback** — Si alguien reacciona con 👍❤️🔥 a una respuesta del bot, esa respuesta sube de score. Si reacciona con 👎❌, baja. Las respuestas con buen score se inyectan como ejemplos few-shot en futuras respuestas.

3. **Historial** — Cada respuesta enviada se guarda con el mensaje que la provocó. El bot usa las mejores como referencia de tono y estilo.

## Instalación

### 1. Clonar el repo
```bash
git clone https://github.com/SASbot01/Agente-Discord.git
cd Agente-Discord
```

### 2. Crear entorno virtual e instalar dependencias
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Configurar tokens
```bash
cp .env.example .env
```
Editar `.env` con:
- `DISCORD_TOKEN` — Token del bot (Discord Developer Portal → Bot → Reset Token)
- `ANTHROPIC_API_KEY` — API key de Anthropic (console.anthropic.com)
- `OWNER_DISCORD_ID` — Tu ID de usuario de Discord

### 4. Configurar la comunidad
Editar `config/communities/creator_founder.json`:
- `server_id` — ID del servidor
- `channel_id` en cada canal — IDs de los canales
- `user_id` en miembros clave — IDs de los usuarios importantes

### 5. (Opcional) Entrenar personalidad con chats reales
Exportar chats con [DiscordChatExporter](https://github.com/Tyrrrz/DiscordChatExporter) en formato JSON, ponerlos en `data/training/` y ejecutar:
```bash
python -m src.trainer TU_USER_ID "Tu Nombre" "Descripción de cómo eres"
```

### 6. Arrancar
```bash
bash start.sh
```

## Comandos

| Acción | Comando |
|---|---|
| Arrancar (background) | `bash start.sh` |
| Parar | `bash stop.sh` |
| Ver logs en tiempo real | `tail -f bot.log` |
| Arrancar en primer plano | `source .venv/bin/activate && python3 main.py` |

## Configuración

### `personality.json`
Define cómo habla el bot: tono, muletillas, emojis favoritos, ejemplos de respuestas reales, cosas que nunca diría.

### `communities/creator_founder.json`
Define el servidor: canales activos, miembros clave, reglas de respuesta, enlaces oficiales, respuestas predefinidas para preguntas frecuentes.

### Variables de entorno (`.env`)
| Variable | Descripción |
|---|---|
| `DISCORD_TOKEN` | Token del bot de Discord |
| `ANTHROPIC_API_KEY` | API key de Anthropic |
| `OWNER_DISCORD_ID` | ID del dueño del bot |
| `RATE_LIMIT_PER_DAY` | Máximo de respuestas por día (default: 15) |

## Añadir más servidores

1. Duplicar `config/communities/creator_founder.json`
2. Cambiar `server_id`, canales, miembros y tono
3. Invitar el bot al nuevo servidor
4. Reiniciar: `bash stop.sh && bash start.sh`
