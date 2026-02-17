"""
Importador de chats exportados de Discord.

Procesa archivos JSON exportados con DiscordChatExporter y genera
un perfil de personalidad basado en los mensajes del usuario.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

CONFIG_DIR = Path(__file__).parent.parent / "config"
TRAINING_DIR = Path(__file__).parent.parent / "data" / "training"


def load_exported_chat(file_path: str) -> list[dict]:
    """Carga un chat exportado en formato JSON de DiscordChatExporter."""
    with open(file_path, encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict) and "messages" in data:
        return data["messages"]
    elif isinstance(data, list):
        return data
    else:
        raise ValueError(f"Formato no reconocido en {file_path}")


def extract_user_messages(messages: list[dict], user_id: str) -> list[dict]:
    """Extrae solo los mensajes de un usuario específico."""
    user_msgs = []
    for msg in messages:
        author = msg.get("author", {})
        msg_user_id = str(author.get("id", ""))
        if msg_user_id == user_id:
            content = msg.get("content", "").strip()
            if content and len(content) > 2:  # Ignorar mensajes muy cortos
                user_msgs.append(
                    {
                        "content": content,
                        "timestamp": msg.get("timestamp", ""),
                        "channel": msg.get("channel", {}).get("name", ""),
                    }
                )
    return user_msgs


def analyze_style(messages: list[dict]) -> dict:
    """Analiza el estilo de escritura basado en mensajes reales."""
    all_text = [m["content"] for m in messages]

    # Longitud promedio de mensaje
    lengths = [len(t) for t in all_text]
    avg_length = sum(lengths) / len(lengths) if lengths else 0

    # Emojis más usados
    emoji_pattern = re.compile(
        r"[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff"
        r"\U0001f680-\U0001f6ff\U0001f900-\U0001f9ff"
        r"\U0001fa00-\U0001fa6f\U0001fa70-\U0001faff"
        r"\u2600-\u26ff\u2700-\u27bf]",
        re.UNICODE,
    )
    all_emojis = []
    for text in all_text:
        all_emojis.extend(emoji_pattern.findall(text))
    top_emojis = [e for e, _ in Counter(all_emojis).most_common(10)]

    # Palabras más frecuentes (excluyendo stop words)
    stop_words = {
        "de", "la", "el", "en", "y", "a", "que", "es", "se", "no",
        "un", "una", "los", "las", "por", "con", "para", "lo", "me",
        "mi", "te", "tu", "le", "al", "del", "ya", "si", "pero",
        "the", "a", "an", "is", "it", "to", "in", "of", "and", "i",
        "you", "he", "she", "we", "they", "my", "your", "do", "does",
    }
    words = []
    for text in all_text:
        for word in re.findall(r"\b\w+\b", text.lower()):
            if word not in stop_words and len(word) > 2:
                words.append(word)
    top_words = [w for w, _ in Counter(words).most_common(30)]

    # Detectar muletillas (frases de 2-3 palabras repetidas)
    bigrams = []
    for text in all_text:
        text_words = text.lower().split()
        for i in range(len(text_words) - 1):
            bigram = f"{text_words[i]} {text_words[i+1]}"
            if all(w not in stop_words for w in bigram.split()):
                bigrams.append(bigram)
    top_bigrams = [b for b, c in Counter(bigrams).most_common(15) if c > 2]

    # Uso de mayúsculas
    caps_msgs = sum(1 for t in all_text if t == t.upper() and len(t) > 5)
    uses_caps = caps_msgs / len(all_text) if all_text else 0

    # Uso de signos
    exclamation_rate = sum(t.count("!") for t in all_text) / len(all_text) if all_text else 0
    question_rate = sum(t.count("?") for t in all_text) / len(all_text) if all_text else 0

    # Mensajes de ejemplo variados (cortos, medianos, largos)
    sorted_by_len = sorted(messages, key=lambda m: len(m["content"]))
    examples = []
    if len(sorted_by_len) > 10:
        # Tomar muestras de diferentes longitudes
        n = len(sorted_by_len)
        indices = [n // 4, n // 2, 3 * n // 4]
        for i in indices:
            examples.append(sorted_by_len[i]["content"])
    else:
        examples = [m["content"] for m in sorted_by_len[:5]]

    return {
        "total_mensajes_analizados": len(messages),
        "longitud_promedio": round(avg_length),
        "emojis_favoritos": top_emojis,
        "palabras_frecuentes": top_words,
        "muletillas_detectadas": top_bigrams,
        "usa_mayusculas_frecuente": uses_caps > 0.1,
        "tasa_exclamaciones": round(exclamation_rate, 2),
        "tasa_preguntas": round(question_rate, 2),
        "ejemplos_reales": examples,
    }


def generate_personality_profile(
    messages: list[dict], nombre: str, descripcion: str
) -> dict:
    """Genera un perfil de personalidad a partir del análisis."""
    style = analyze_style(messages)

    # Determinar tono
    if style["tasa_exclamaciones"] > 1:
        tono = "muy expresivo y energético"
    elif style["tasa_exclamaciones"] > 0.3:
        tono = "casual y expresivo"
    elif style["longitud_promedio"] > 100:
        tono = "detallado y conversacional"
    else:
        tono = "directo y conciso"

    profile = {
        "nombre": nombre,
        "descripcion": descripcion,
        "tono_general": tono,
        "idioma_principal": "es",
        "muletillas": style["muletillas_detectadas"][:5],
        "emojis_favoritos": style["emojis_favoritos"][:5],
        "palabras_frecuentes": style["palabras_frecuentes"][:15],
        "longitud_tipica_mensaje": style["longitud_promedio"],
        "nunca_dirias": [
            "Completar manualmente con cosas que nunca dirías"
        ],
        "ejemplos_respuestas": [
            {
                "contexto": "Mensaje real extraído",
                "mensaje_usuario": "(completar con contexto)",
                "tu_respuesta": ejemplo,
            }
            for ejemplo in style["ejemplos_reales"][:5]
        ],
        "_analisis_automatico": style,
    }

    return profile


def process_training_data(user_id: str, nombre: str, descripcion: str):
    """Procesa todos los archivos de training y genera el perfil."""
    all_messages = []

    training_files = list(TRAINING_DIR.glob("*.json"))
    if not training_files:
        print(f"No se encontraron archivos JSON en {TRAINING_DIR}")
        print("Exporta tus chats con DiscordChatExporter y ponlos ahí.")
        return

    for file in training_files:
        print(f"Procesando: {file.name}")
        try:
            messages = load_exported_chat(str(file))
            user_msgs = extract_user_messages(messages, user_id)
            print(f"  → {len(user_msgs)} mensajes tuyos encontrados")
            all_messages.extend(user_msgs)
        except Exception as e:
            print(f"  → Error: {e}")

    if not all_messages:
        print(f"\nNo se encontraron mensajes del usuario {user_id}")
        print("Verifica que el user_id sea correcto.")
        return

    print(f"\nTotal: {len(all_messages)} mensajes tuyos")
    print("Analizando estilo de escritura...")

    profile = generate_personality_profile(all_messages, nombre, descripcion)

    # Guardar perfil
    output_path = CONFIG_DIR / "personality.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(profile, f, ensure_ascii=False, indent=2)

    print(f"\nPerfil guardado en: {output_path}")
    print(f"\nResumen del análisis:")
    print(f"  Mensajes analizados: {profile['_analisis_automatico']['total_mensajes_analizados']}")
    print(f"  Longitud promedio: {profile['_analisis_automatico']['longitud_promedio']} chars")
    print(f"  Tono detectado: {profile['tono_general']}")
    print(f"  Emojis favoritos: {' '.join(profile['emojis_favoritos'])}")
    print(f"  Muletillas: {', '.join(profile['muletillas'])}")
    print(f"\n¡Revisa el archivo y ajusta 'nunca_dirias' y los ejemplos manualmente!")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Uso: python -m src.trainer <tu_user_id> <tu_nombre> <descripción>")
        print('Ejemplo: python -m src.trainer 123456789 "Juan" "Dev que le gusta el café"')
        sys.exit(1)

    user_id = sys.argv[1]
    nombre = sys.argv[2]
    descripcion = " ".join(sys.argv[3:])
    process_training_data(user_id, nombre, descripcion)
