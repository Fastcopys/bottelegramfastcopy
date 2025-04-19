import logging
import json
import os
import requests
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    constants,
    BotCommand
)
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from urllib.parse import quote
from flask import Flask
from threading import Thread
from datetime import datetime, timedelta

# Configuración
TOKEN = "8053274411:AAFgsGcQbwhO-scWXKT53EFK8ppXDoAumKw"
TMDB_API_KEY = "e66f746066477bafd72948093806e1a6"
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
ADMIN_ID = 7302458830
WHATSAPP_NUM = "+5352425434"
JSON_FILE = "user_data.json"

# Configurar servidor web
app = Flask(__name__)
port = int(os.environ.get('PORT', 5000))

@app.route('/')
def home():
    return "Bot en funcionamiento", 200

def run_flask():
    app.run(host='0.0.0.0', port=port)

# Almacenamiento en JSON
pending_requests = set()

def load_users():
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}
    return {}

def save_users(data):
    try:
        with open(JSON_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except IOError as e:
        logging.error(f"Error guardando datos: {str(e)}")

# Configurar logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

async def post_init(application: Application):
    await application.bot.set_my_commands([
        BotCommand("start", "Menú principal")
        # Comando "estrenos" eliminado
    ])

async def check_user_limit(user_id: int) -> bool:
    user_searches = load_users()
    user_data = user_searches.get(str(user_id), {'count': 0, 'granted': 0})
    allowed = 5 + user_data['granted']
    return user_data['count'] < allowed

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    user_searches = load_users()
    
    if user_id not in user_searches:
        user_searches[user_id] = {'count': 0, 'granted': 0}
        save_users(user_searches)
    
    remaining = 5 + user_searches[user_id]['granted'] - user_searches[user_id]['count']
    
    keyboard = [
        [InlineKeyboardButton("🎬 Buscar Película", callback_data="search_type:movie"),
         InlineKeyboardButton("📺 Buscar Serie", callback_data="search_type:tv")],
        [InlineKeyboardButton("🎉 Últimos Estrenos", callback_data="releases_menu")]
    ]
    
    if int(user_id) == ADMIN_ID:
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
    user_id = str(query.from_user.id)
    user_searches = load_users()
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
    
    user_searches = load_users()
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
    _, search_type = query.data.split(':')
    context.user_data['search_type'] = search_type
    
    # Log selection for debugging
    logger.info(f"User selected search type: {search_type}")
    
    await query.edit_message_text(
        text=f"🔍 Escribe el título de la {'película' if search_type == 'movie' else 'serie'}:")

async def handle_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
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
        await update.message.reply_text("⚠️ Primero selecciona un tipo de búsqueda")
        return
    
    try:
        user_query = update.message.text
        # Set the query as context.args for buscar_media
        context.args = [user_query]
        
        # Log the search type and query to help debug
        logger.info(f"Searching for {search_type}: {user_query}")
        
        # Make sure we're calling buscar_media with the correct media_type
        await buscar_media(update, context, media_type=search_type)
    except Exception as e:
        logger.error(f"Error en handle_search: {str(e)}")
    finally:
        # Clear the search_type after search is complete
        context.user_data.pop('search_type', None)

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
        logger.error(f"URL: {BASE_URL}{endpoint}")
        logger.error(f"Params: {params}")
        return None

async def show_results(message, results, title, media_type):
    results_to_show = results[:20]
    media_groups = []
    current_media_group = []
    buttons = []
    
    for idx, result in enumerate(results_to_show, start=1):
        media_id = result['id']
        item_title = result.get('title') or result.get('name') or 'Sin título'
        year = (result.get('release_date') or result.get('first_air_date') or '')[:4] or 'N/A'
        rating = result.get('vote_average', '?')
        poster_path = result.get('poster_path', '')
        media_emoji = '🎬' if media_type == 'movie' else '📺'
        
        # Añadir el número al caption para mejor correspondencia
        caption = (
            f"✨ *#{idx} - {item_title}* ({year})\n\n"
            f"{media_emoji} Tipo: {'Película' if media_type == 'movie' else 'Serie'}\n"
            f"⭐ Puntuación: {rating}/10\n"
            f"🌍 Idioma: {result.get('original_language', '').upper()}"
        )
        
        current_media_group.append(
            InputMediaPhoto(
                media=f"{IMAGE_BASE_URL}{poster_path}" if poster_path else "https://via.placeholder.com/500x750?text=Imagen+no+disponible",
                caption=caption,
                parse_mode='Markdown'
            )
        )
        
        if idx % 2 == 1:
            button_row = []
            
        button_text = f"{idx}. {item_title[:15]}..."
        button_row.append(InlineKeyboardButton(
            button_text,
            callback_data=f"{media_type}|{media_id}"
        ))
        
        if idx % 2 == 0 or idx == len(results_to_show):
            buttons.append(button_row)
        
        if len(current_media_group) == 10 or idx == len(results_to_show):
            media_groups.append(current_media_group)
            current_media_group = []
    
    for group in media_groups:
        try:
            await message.reply_media_group(group)
        except Exception as e:
            logger.error(f"Error enviando media group: {str(e)}")
    
    await message.reply_text(
        f"🎉 *{title}*\n"
        "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n"
        "Selecciona una opción:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    media_type, media_id = query.data.split('|')
    await query.message.edit_reply_markup(reply_markup=None)
    
    # Log the selection for debugging
    logger.info(f"User selected {media_type} with ID: {media_id}")
    
    endpoint = f"/{media_type}/{media_id}"
    details_es = await fetch_tmdb_data(endpoint, {"language": "es-ES"})
    details = details_es or await fetch_tmdb_data(endpoint)
    
    if not details:
        await query.message.reply_text("❌ Error al obtener detalles")
        return

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
    user_id = str(update.effective_user.id)
    user_searches = load_users()
    
    try:
        user_searches[user_id]['count'] += 1
        save_users(user_searches)
        
        query = ' '.join(context.args)
        if not query:
            await update.message.reply_text('⚠️ Por favor escribe un título válido')
            return

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=constants.ChatAction.UPLOAD_PHOTO
        )

        # Log the API call for debugging
        logger.info(f"Searching for {media_type} with query: {query}")

        search_params = {
            "query": query,
            "language": "es-ES",
            "include_adult": False,
            "region": "ES"
        }
        
        # Make the API call to search for the series/movie
        search_data = await fetch_tmdb_data(
            f"/search/{media_type}",
            search_params
        )
        
        # Log the response to see if we're getting results
        if search_data and 'results' in search_data:
            logger.info(f"Results for {media_type}: {len(search_data['results'])} items found")
        else:
            logger.error(f"No results or invalid response for {media_type} search: {search_data}")
        
        if not search_data or not search_data.get('results'):
            await update.message.reply_text(f"⚠️ No se encontraron resultados para: {query}")
            return

        # Show the results to the user
        await show_results(update.message, search_data['results'], query, media_type)

        # Check remaining searches
        remaining = 5 + user_searches[user_id]['granted'] - user_searches[user_id]['count']
        if remaining == 2:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ User {user_id} tiene {remaining} búsquedas restantes"
            )

    except Exception as e:
        logger.error(f"Error en buscar_media: {str(e)}")
        # Rollback the search count if there was an error
        user_searches[user_id]['count'] -= 1
        save_users(user_searches)
        await update.message.reply_text('❌ Error procesando tu solicitud')

async def credito(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Comando restringido")
        return

    if len(context.args) != 2:
        await update.message.reply_text("Formato: /credito <user_id> <cantidad>")
        return

    try:
        user_id = str(context.args[0])
        amount = int(context.args[1])
        if amount < 1:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Cantidad inválida")
        return

    user_searches = load_users()
    
    if user_id not in user_searches:
        user_searches[user_id] = {'count': 0, 'granted': 0}

    user_searches[user_id]['granted'] += amount
    pending_requests.discard(user_id)
    save_users(user_searches)
    
    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"🎉 +{amount} créditos otorgados!\nNuevo total: {5 + user_searches[user_id]['granted'] - user_searches[user_id]['count']}"
        )
    except Exception as e:
        logger.error(f"Error notificando usuario: {str(e)}")

    await update.message.reply_text(f"✅ Usuario {user_id} actualizado")

async def show_releases_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🕐 1 Mes", callback_data="period:1"),
         InlineKeyboardButton("🕑 2 Meses", callback_data="period:2")],
        [InlineKeyboardButton("🕒 3 Meses", callback_data="period:3"),
         InlineKeyboardButton("🔙 Menú Principal", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        text="⏳ Selecciona el período temporal:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_period_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    months = int(query.data.split(':')[1])
    context.user_data['release_period'] = months
    
    keyboard = [
        [InlineKeyboardButton("🎬 Películas", callback_data=f"content_type:{months}:movie"),
         InlineKeyboardButton("📺 Series", callback_data=f"content_type:{months}:tv")],
        [InlineKeyboardButton("🍿 Ambos", callback_data=f"content_type:{months}:both"),
         InlineKeyboardButton("🔙 Atrás", callback_data="releases_menu")]
    ]
    
    await query.edit_message_text(
        text=f"📌 Período seleccionado: {months} mes(es)\n¿Qué tipo de contenido deseas ver?",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_content_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if not await check_user_limit(user_id):
        await query.message.reply_text("⚠️ Límite de búsquedas alcanzado")
        return
    
    _, months, content_type = query.data.split(':')
    months = int(months)
    
    end_date = datetime.today()
    start_date = end_date - timedelta(days=30*months)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    user_searches = load_users()
    user_searches[user_id]['count'] += 1
    save_users(user_searches)
    
    await context.bot.send_chat_action(
        chat_id=query.message.chat_id,
        action=constants.ChatAction.UPLOAD_PHOTO
    )
    
    results = []
    
    if content_type in ['movie', 'both']:
        movie_params = {
            "primary_release_date.gte": start_str,
            "primary_release_date.lte": end_str,
            "sort_by": "popularity.desc",
            "language": "es-ES",
            "page": 1
        }
        movie_data = await fetch_tmdb_data("/discover/movie", movie_params)
        if movie_data and movie_data.get('results'):
            results.extend([(item, 'movie') for item in movie_data['results'][:10]])
    
    if content_type in ['tv', 'both']:
        tv_params = {
            "first_air_date.gte": start_str,
            "first_air_date.lte": end_str,
            "sort_by": "popularity.desc",
            "language": "es-ES",
            "page": 1
        }
        tv_data = await fetch_tmdb_data("/discover/tv", tv_params)
        if tv_data and tv_data.get('results'):
            results.extend([(item, 'tv') for item in tv_data['results'][:10]])
    
    if not results:
        await query.message.reply_text("❌ No se encontraron resultados para este período")
        return
    
    await show_mixed_results(query.message, results, months, content_type)

async def show_mixed_results(message, results, months, content_type):
    media_groups = []
    current_media_group = []
    buttons = []
    
    content_types = {
        'movie': '🎬 Películas',
        'tv': '📺 Series',
        'both': '🍿 Películas y Series'
    }
    
    title = f"{content_types[content_type]} ({months} mes(es))"
    
    for idx, (result, media_type) in enumerate(results[:20], start=1):
        media_id = result['id']
        item_title = result.get('title') or result.get('name') or 'Sin título'
        year = (result.get('release_date') or result.get('first_air_date') or '')[:4] or 'N/A'
        rating = result.get('vote_average', '?')
        poster_path = result.get('poster_path', '')
        media_emoji = '🎬' if media_type == 'movie' else '📺'
        
        # Añadir numeración al caption para mejor correspondencia
        caption = (
            f"✨ *#{idx} - {item_title}* ({year})\n\n"
            f"{media_emoji} Tipo: {'Película' if media_type == 'movie' else 'Serie'}\n"
            f"⭐ Puntuación: {rating}/10\n"
            f"🌍 Idioma: {result.get('original_language', '').upper()}"
        )
        
        current_media_group.append(
            InputMediaPhoto(
                media=f"{IMAGE_BASE_URL}{poster_path}" if poster_path else "https://via.placeholder.com/500x750?text=Imagen+no+disponible",
                caption=caption,
                parse_mode='Markdown'
            )
        )
        
        if idx % 2 == 1:
            button_row = []
            
        button_text = f"{idx}. {media_emoji} {item_title[:15]}..."
        button_row.append(InlineKeyboardButton(
            button_text,
            callback_data=f"{media_type}|{media_id}"
        ))
        
        if idx % 2 == 0 or idx == len(results):
            buttons.append(button_row)
        
        if len(current_media_group) == 10 or idx == len(results):
            media_groups.append(current_media_group)
            current_media_group = []
    
    for group in media_groups:
        try:
            await message.reply_media_group(group)
        except Exception as e:
            logger.error(f"Error enviando media group: {str(e)}")
    
    await message.reply_text(
        f"🎉 *{title}*\n"
        "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n"
        "Selecciona para ver detalles:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    # Crear un nuevo Update con message establecido para poder llamar a start()
    update.message = query.message
    await start(update, context)

async def estrenos_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Simplemente redirigir al menú de estrenos
    fake_query = update.callback_query = type('obj', (object,), {
        'answer': lambda: None,
        'edit_message_text': lambda text, reply_markup: update.message.reply_text(text, reply_markup=reply_markup)
    })
    
    await show_releases_menu(update, context)

def main():
    Thread(target=run_flask, daemon=True).start()
    
    application = Application.builder() \
        .token(TOKEN) \
        .post_init(post_init) \
        .build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("estrenos", estrenos_command))
    application.add_handler(CommandHandler("credito", credito))
    
    application.add_handler(CallbackQueryHandler(select_search_type, pattern=r"^search_type:"))
    application.add_handler(CallbackQueryHandler(handle_selection, pattern=r"^movie\|.+|^tv\|.+"))
    application.add_handler(CallbackQueryHandler(show_user_status, pattern=r"^user_status"))
    application.add_handler(CallbackQueryHandler(show_admin_stats, pattern=r"^admin_stats"))
    application.add_handler(CallbackQueryHandler(show_releases_menu, pattern=r"^releases_menu"))
    application.add_handler(CallbackQueryHandler(handle_period_selection, pattern=r"^period:\d+"))
    application.add_handler(CallbackQueryHandler(handle_content_selection, pattern=r"^content_type:\d+:(movie|tv|both)"))
    application.add_handler(CallbackQueryHandler(back_to_main, pattern=r"^back_to_main"))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))

    application.run_polling()

if __name__ == '__main__':
    main()