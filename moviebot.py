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

# Configuración - Reemplazar con tus datos
TOKEN = "8053274411:AAFgsGcQbwhO-scWXKT53EFK8ppXDoAumKw"
TMDB_API_KEY = "e66f746066477bafd72948093806e1a6"
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🎬 Buscar Película", callback_data="search_type:movie")],
        [InlineKeyboardButton("📺 Buscar Serie/Novela", callback_data="search_type:tv")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        '🎬 FastCopy Bot - Menú Principal\n'
        '▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n'
        'Selecciona el tipo de contenido:',
        parse_mode='Markdown',
        reply_markup=reply_markup
    )

async def select_search_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    search_type = query.data.split(':')[1]
    context.user_data['search_type'] = search_type
    
    await query.edit_message_text(
        text=f"🔍 Escribe el título de la {'película' if search_type == 'movie' else 'serie/novela'}:"
    )

async def handle_search_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'search_type' not in context.user_data:
        return
    
    search_type = context.user_data['search_type']
    user_query = update.message.text
    context.args = [user_query]
    
    try:
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
            f"{media_emoji} Tipo: {'Película' if media_type == 'movie' else 'Serie/Novela'}\n"
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
        countries = ', '.join([c['name'] for c in details.get('production_countries', [])][:3])
        overview = details.get('overview', 'Sin descripción disponible').replace('_', '\\_').replace('*', '\\*')
        
        details_text = (
            f"🎞 *{title}* ({release_date})\n\n"
            "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n\n"
            f"📝 *Título Original:* {original_title}\n"
            f"⏳ *Duración:* {runtime} minutos\n"
            f"⭐ *Puntuación:* {details.get('vote_average', 'N/A')}/10\n"
            f"🎭 *Géneros:* {genres}\n"
            f"🌍 *Países:* {countries}\n\n"
            f"📖 *Sinopsis:*\n{overview}"
        )
        
        whatsapp_text = (
            f"*🎬FastCopy🎬*\n\n"
            f"📽 *Título:* {title}\n"
            f"🎞 *Título Original:* {original_title}\n"
            f"🗓 *Año:* {release_date}\n"
            f"⏳ *Duración:* {runtime} minutos\n"
            f"⭐ *Puntuación:* {details.get('vote_average', 'N/A')}/10\n"
            f"🎭 *Géneros:* {genres}\n"
            f"🌍 *Países:* {countries}\n\n"
            f"📖 *Sinopsis:*\n{overview}\n\n"
        )
    else:
        title = details.get('name', 'Sin título')
        original_title = details.get('original_name', title)
        first_air = (details.get('first_air_date', '')[:4] if details.get('first_air_date') else 'N/A')
        last_air = (details.get('last_air_date', '')[:4] if details.get('last_air_date') else 'N/A')
        seasons = details.get('number_of_seasons', 'N/A')
        episodes = details.get('number_of_episodes', 'N/A')
        genres = ', '.join([g['name'] for g in details.get('genres', [])][:3])
        countries = ', '.join([c['name'] for c in details.get('production_countries', [])][:3])
        overview = details.get('overview', 'Sin descripción disponible').replace('_', '\\_').replace('*', '\\*')
        
        # Detalles por temporada
        season_details = []
        if seasons != 'N/A':
            for season in details.get('seasons', []):
                if season['season_number'] > 0:
                    season_details.append(
                        f"• Temp. {season['season_number']}: {season['episode_count']} capítulos"
                    )
        
        season_info = '\n'.join(season_details[:100]) if season_details else 'Información no disponible'

        details_text = (
            f"📺 *{title}* ({first_air}-{last_air})\n\n"
            "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n\n"
            f"📝 *Título Original:* {original_title}\n"
            f"📅 *Temporadas:* {seasons}\n"
            f"🎬 *Episodios totales:* {episodes}\n"
            f"⭐ *Puntuación:* {details.get('vote_average', 'N/A')}/10\n"
            f"🎭 *Géneros:* {genres}\n"
            f"🌍 *Países:* {countries}\n\n"
            f"📑 *Detalles por temporada:*\n{season_info}\n\n"
            f"📖 *Sinopsis:*\n{overview}"
        )
        
        whatsapp_text = (
            f"*🎬FastCopy🎬*\n\n"
            f"📺 *Título:* {title}\n"
            f"🎞 *Título Original:* {original_title}\n"
            f"🗓 *Emisión:* {first_air}-{last_air}\n"
            f"📅 *Temporadas:* {seasons}\n"
            f"🎬 *Episodios totales:* {episodes}\n"
            f"⭐ *Puntuación:* {details.get('vote_average', 'N/A')}/10\n"
            f"🎭 *Géneros:* {genres}\n"
            f"🌍 *Países:* {countries}\n\n"
            f"📑 *Detalles por temporada:*\n{season_info}\n\n"
            f"📖 *Sinopsis:*\n{overview}\n\n"
        )

    # Crear enlace de WhatsApp
    whatsapp_link = f"https://wa.me/?text={quote(whatsapp_text)}"
    
    # Teclado con botón WhatsApp
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Compartir por WhatsApp", url=whatsapp_link)]
    ])

    # Enviar mensaje
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
    try:
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

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        await update.message.reply_text('❌ Error procesando tu solicitud')

def main():
    application = (
        Application.builder()
        .token(TOKEN)
        .post_init(post_init)
        .job_queue(None)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", start))
    application.add_handler(CallbackQueryHandler(select_search_type, pattern=r"^search_type:"))
    application.add_handler(CallbackQueryHandler(handle_selection, pattern=r"^movie\|.+|^tv\|.+"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search_query))

    application.run_polling()

if __name__ == '__main__':
    main()