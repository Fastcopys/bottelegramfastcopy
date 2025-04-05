import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    constants,
    BotCommand
)
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import requests
from urllib.parse import quote
from flask import Flask
from threading import Thread
import os

# Configuración
TOKEN = "8053274411:AAFgsGcQbwhO-scWXKT53EFK8ppXDoAumKw"
TMDB_API_KEY = "e66f746066477bafd72948093806e1a6"
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
ADMIN_ID = 7302458830
WHATSAPP_NUM = "+5352425434"

# Configurar servidor web para mantener activo
app = Flask(__name__)
port = int(os.environ.get('PORT', 5000))

@app.route('/')
def home():
    return "Bot en funcionamiento", 200

def run_flask():
    app.run(host='0.0.0.0', port=port)

# Almacenamiento en memoria
user_searches = {}
pending_requests = set()

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "Menú principal"),
        BotCommand("help", "Ayuda")
    ])

async def check_user_limit(user_id: int) -> bool:
    if user_id not in user_searches:
        user_searches[user_id] = {'count': 0, 'granted': 0}
    allowed = 5 + user_searches[user_id]['granted']
    return user_searches[user_id]['count'] < allowed

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_searches:
        user_searches[user_id] = {'count': 0, 'granted': 0}
    
    remaining = 5 + user_searches[user_id]['granted'] - user_searches[user_id]['count']
    
    keyboard = [
        [InlineKeyboardButton("🎬 Buscar Película", callback_data="search_type:movie"),
         InlineKeyboardButton("📺 Buscar Serie", callback_data="search_type:tv")]
    ]
    
    if user_id == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📊 Estadísticas Admin", callback_data="admin_stats")])
    else:
        keyboard.append([InlineKeyboardButton("📈 Mi Estado", callback_data="user_status")])
    
    text = (
        f'🎬 FastCopy Bot - Menú Principal\n'
        f'▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n'
        f'Búsquedas restantes: {remaining}'
    )
    
    await update.message.reply_text(
        text,
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_user_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = user_searches.get(user_id, {'count': 0, 'granted': 0})
    remaining = 5 + data['granted'] - data['count']
    
    status_text = (
        f"📊 *Tu Estado*\n\n"
        f"🆔 ID de Usuario: `{user_id}`\n"
        f"🔍 Búsquedas realizadas: {data['count']}\n"
        f"🎯 Límite total: {5 + data['granted']}\n"
        f"💎 Créditos restantes: {remaining}"
    )
    
    await query.edit_message_text(
        text=status_text,
        parse_mode='Markdown'
    )

async def show_admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        await query.message.reply_text("❌ Acceso no autorizado")
        return
    
    stats_text = "📈 *Estadísticas Globales*\n\n"
    for user_id, data in user_searches.items():
        stats_text += (
            f"👤 User `{user_id}`:\n"
            f"- Búsquedas: {data['count']}\n"
            f"- Créditos: {data['granted']}\n"
            f"- Disponibles: {5 + data['granted'] - data['count']}\n\n"
        )
    
    stats_text += f"🔄 Solicitudes pendientes: {len(pending_requests)}"
    await query.edit_message_text(
        text=stats_text,
        parse_mode='Markdown'
    )

async def select_search_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    search_type = query.data.split(':')[1]
    context.user_data['search_type'] = search_type
    
    await query.edit_message_text(
        text=f"🔍 Escribe el título de la {'película' if search_type == 'movie' else 'serie'}:")

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not await check_user_limit(user_id):
        message = f"Usuario {user_id} solicita más créditos"
        whatsapp_url = f"https://wa.me/{WHATSAPP_NUM}?text={quote(message)}"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 Contactar al Admin", url=whatsapp_url)]
        ])
        
        await update.message.reply_text(
            "⚠️ Límite de búsquedas alcanzado\nContacta al administrador:",
            reply_markup=keyboard)
        
        if user_id not in pending_requests:
            pending_requests.add(user_id)
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ Solicitud de créditos:\nUser ID: {user_id}\nUsa /credito {user_id} <cantidad>"
            )
        return
    
    search_type = context.user_data.get('search_type')
    if not search_type:
        return
    
    try:
        user_query = update.message.text
        context.args = [user_query]
        await buscar_media(update, context, media_type=search_type)
    finally:
        del context.user_data['search_type']

async def fetch_tmdb_data(endpoint, params=None):
    params = params or {}
    params["api_key"] = TMDB_API_KEY
    
    try:
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            params=params,
            timeout=15
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"Error en la API: {str(e)}")
        return None

async def show_results(update, results, query, media_type):
    media_group = []
    keyboard = []
    
    for idx, result in enumerate(results[:5], start=1):
        media_id = result['id']
        title = result.get('title') or result.get('name') or 'Sin título'
        year = (result.get('release_date') or result.get('first_air_date') or '')[:4] or 'N/A'
        rating = result.get('vote_average', '?')
        poster_path = result.get('poster_path', '')
        media_emoji = '🎬' if media_type == 'movie' else '📺'
        
        caption = (
            f"✨ *{title}* ({year})\n\n"
            f"{media_emoji} Tipo: {'Película' if media_type == 'movie' else 'Serie'}\n"
            f"⭐ Puntuación: {rating}/10\n"
            f"🌍 Idioma: {result.get('original_language', '').upper()}"
        )
        
        media_group.append(
            InputMediaPhoto(
                media=f"{IMAGE_BASE_URL}{poster_path}" if poster_path else "https://via.placeholder.com/500x750?text=Imagen+no+disponible",
                caption=caption,
                parse_mode='Markdown'
            )
        )
        
        keyboard.append([
            InlineKeyboardButton(
                f"{idx}. {title[:15]}... ({year}) {media_emoji}",
                callback_data=f"{media_type}|{media_id}"
            )
        ])
    
    await update.message.reply_media_group(media_group)
    await update.message.reply_text(
        f"🎉 *Resultados para:* `{query}`\n"
        "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n"
        "Selecciona una opción:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    media_type, media_id = query.data.split('|')
    await query.message.edit_reply_markup(reply_markup=None)
    
    # Obtener detalles
    endpoint = f"/{media_type}/{media_id}"
    details_es = await fetch_tmdb_data(endpoint, {"language": "es-ES"})
    details = details_es or await fetch_tmdb_data(endpoint)
    
    if not details:
        await query.message.reply_text("❌ Error al obtener detalles")
        return

    # Construir mensaje
    if media_type == 'movie':
        title = details.get('title', 'Sin título')
        original_title = details.get('original_title', title)
        release_date = details.get('release_date', 'N/A')[:4] if details.get('release_date') else 'N/A'
        runtime = details.get('runtime', 'N/A')
        genres = ', '.join([g['name'] for g in details.get('genres', [])][:3])
        overview = details.get('overview', 'Sin descripción disponible').replace('_', '\\_').replace('*', '\\*')
        
        details_text = (
            f"🎞 *{title}* ({release_date})\n\n"
            "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n\n"
            f"📝 *Título Original:* {original_title}\n"
            f"⏳ *Duración:* {runtime} minutos\n"
            f"⭐ *Puntuación:* {details.get('vote_average', 'N/A')}/10\n"
            f"🎭 *Géneros:* {genres}\n\n"
            f"📖 *Sinopsis:*\n{overview}"
        )
    else:
        title = details.get('name', 'Sin título')
        original_title = details.get('original_name', title)
        first_air = (details.get('first_air_date', '')[:4] if details.get('first_air_date') else 'N/A')
        seasons = details.get('number_of_seasons', 'N/A')
        episodes = details.get('number_of_episodes', 'N/A')
        genres = ', '.join([g['name'] for g in details.get('genres', [])][:3])
        overview = details.get('overview', 'Sin descripción disponible').replace('_', '\\_').replace('*', '\\*')
        
        details_text = (
            f"📺 *{title}*\n\n"
            "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n\n"
            f"📝 *Título Original:* {original_title}\n"
            f"📅 *Temporadas:* {seasons}\n"
            f"🎬 *Episodios totales:* {episodes}\n"
            f"⭐ *Puntuación:* {details.get('vote_average', 'N/A')}/10\n"
            f"🎭 *Géneros:* {genres}\n\n"
            f"📖 *Sinopsis:*\n{overview}"
        )

    whatsapp_text = f"*🎬FastCopy🎬*\n\n{details_text.replace('*', '')}"
    whatsapp_link = f"https://wa.me/?text={quote(whatsapp_text)}"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Compartir por WhatsApp", url=whatsapp_link)]
    ])

    try:
        poster_path = details.get('poster_path')
        if poster_path:
            await query.message.reply_photo(
                photo=f"{IMAGE_BASE_URL}{poster_path}",
                caption=details_text,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        else:
            await query.message.reply_text(
                details_text,
                parse_mode='Markdown',
                reply_markup=keyboard
            )
    except Exception as e:
        logger.error(f"Error al enviar: {str(e)}")
        await query.message.reply_text(details_text, parse_mode='Markdown', reply_markup=keyboard)

async def buscar_media(update: Update, context: ContextTypes.DEFAULT_TYPE, media_type: str):
    user_id = update.effective_user.id
    try:
        user_searches[user_id]['count'] += 1
        
        query = ' '.join(context.args)
        if not query:
            await update.message.reply_text('⚠️ Por favor escribe un título válido')
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.UPLOAD_PHOTO
        )

        search_data = await fetch_tmdb_data(
            f"/search/{media_type}",
            {"query": query, "language": "es-ES", "include_adult": False}
        )
        
        if not search_data or not search_data.get('results'):
            await update.message.reply_text(f"⚠️ No se encontraron resultados para: {query}")
            return

        await show_results(update, search_data['results'], query, media_type)

        remaining = 5 + user_searches[user_id]['granted'] - user_searches[user_id]['count']
        if remaining == 2:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ User {user_id} tiene {remaining} búsquedas restantes"
            )

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        user_searches[user_id]['count'] -= 1
        await update.message.reply_text('❌ Error procesando tu solicitud')

async def credito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando restringido")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Formato: /credito <user_id> <cantidad>")
        return

    try:
        user_id = int(context.args[0])
        amount = int(context.args[1])
        if amount < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Cantidad inválida")
        return

    if user_id not in user_searches:
        user_searches[user_id] = {'count': 0, 'granted': 0}

    user_searches[user_id]['granted'] += amount
    pending_requests.discard(user_id)
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 +{amount} créditos otorgados!\nNuevo total: {5 + user_searches[user_id]['granted'] - user_searches[user_id]['count']}"
        )
    except Exception as e:
        logger.error(f"Error notificando usuario: {str(e)}")

    await update.message.reply_text(f"✅ Usuario {user_id} actualizado")

def main():
    # Iniciar servidor web en un hilo separado
    Thread(target=run_flask, daemon=True).start()
    
    # Configurar y ejecutar el bot de Telegram
    application = Application.builder() \
        .token(TOKEN) \
        .post_init(post_init) \
        .job_queue(None) \
        .build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CommandHandler("credito", credito))
    
    application.add_handler(CallbackQueryHandler(select_search_type, pattern=r"^search_type:"))
    application.add_handler(CallbackQueryHandler(handle_selection, pattern=r"^movie\|.+|^tv\|.+"))
    application.add_handler(CallbackQueryHandler(show_user_status, pattern=r"^user_status"))
    application.add_handler(CallbackQueryHandler(show_admin_stats, pattern=r"^admin_stats"))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))

    application.run_polling()

if __name__ == '__main__':
    main()