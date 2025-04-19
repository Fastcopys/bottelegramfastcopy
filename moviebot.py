import logging
import json
import os
import requests
import random
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
from datetime import datetime, timedelta

# Configuración
TOKEN = "8053274411:AAFmo-9z7B8cj-dvBRmJA-vlS0CN0-mq41U"
TMDB_API_KEY = "07579db4e41ee712acd413cad1abb160"
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
ADMIN_ID = 7302458830
WHATSAPP_NUM = "+5352425434"
JSON_FILE = "user_data.json"

COUNTRIES = {
    "TR": "Turquía 🇹🇷",
    "MX": "México 🇲🇽",
    "CO": "Colombia 🇨🇴",
    "CL": "Chile 🇨🇱",
    "BR": "Brasil 🇧🇷",
    "US": "EE.UU. 🇺🇸",
    "ES": "España 🇪🇸",
    "AR": "Argentina 🇦🇷",
    "FR": "Francia 🇫🇷",
    "KR": "Corea 🇰🇷",
    "JP": "Japón 🇯🇵",
    "ANY": "Internacional 🌍"
}

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
    ])

async def check_user_limit(user_id: int) -> bool:
    user_searches = load_users()
    user_data = user_searches.get(str(user_id), {'count': 0, 'granted': 0})
    return user_data['count'] < (5 + user_data['granted'])

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
        [InlineKeyboardButton("🎉 Últimos Estrenos", callback_data="releases_menu"),
         InlineKeyboardButton("🎲 Recomendación Aleatoria", callback_data="random_menu")],
        [InlineKeyboardButton("📈 Mi Estado", callback_data="user_status")]
    ]
    
    if int(user_id) == ADMIN_ID:
        keyboard.append([InlineKeyboardButton("📊 Estadísticas Admin", callback_data="admin_stats")])
    
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
        parse_mode='Markdown')

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
        parse_mode='Markdown')

async def select_search_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, search_type = query.data.split(':')
    context.user_data['search_type'] = search_type
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
        context.args = [user_query]
        await buscar_media(update, context, media_type=search_type)
    except Exception as e:
        logger.error(f"Error en handle_search: {str(e)}")
    finally:
        context.user_data.pop('search_type', None)

async def fetch_tmdb_data(endpoint, params=None):
    params = params or {}
    params.update({
        "api_key": TMDB_API_KEY,
        "language": "es-ES",
        "region": "ES"
    })
    
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

async def fetch_trailer(media_type, media_id):
    videos_data = await fetch_tmdb_data(
        f"/{media_type}/{media_id}/videos",
        {"include_video_language": "es"}
    )
    
    if videos_data and videos_data.get('results'):
        for video in videos_data['results']:
            if video['site'] == 'YouTube' and video['type'] == 'Trailer' and video['iso_639_1'] == 'es':
                return f"https://youtu.be/{video['key']}"
        
        for video in videos_data['results']:
            if video['site'] == 'YouTube' and video['type'] == 'Trailer':
                return f"https://youtu.be/{video['key']}"
    return None

async def show_results(message, results, title, media_type):
    results_to_show = results[:6]
    media_groups = []
    current_media_group = []
    buttons = []
    
    for idx, result in enumerate(results_to_show, start=1):
        media_id = result['id']
        item_title = result.get('title') or result.get('name') or 'Sin título'
        date = result.get('release_date') or result.get('first_air_date') or ''
        year = date[:4] if len(date) >= 4 else 'N/A'
        rating = result.get('vote_average', '?')
        poster_path = result.get('poster_path', '')
        media_emoji = '🎬' if media_type == 'movie' else '📺'
        
        # Obtener país
        if media_type == 'movie':
            country = result.get('production_countries', [{}])[0].get('name', 'N/A')
        else:
            country_code = result.get('origin_country', [''])[0]
            country = COUNTRIES.get(country_code, country_code)
        
        caption = (
            f"✨ *#{idx} - {item_title}* ({year})\n\n"
            f"{media_emoji} Tipo: {'Película' if media_type == 'movie' else 'Serie'}\n"
            f"🌍 País: {country}\n"
            f"⭐ Puntuación: {rating}/10\n"
            f"🗣️ Idioma: {result.get('original_language', '').upper()}"
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
        
        if idx % 2 == 0 or idx == len(results_to_show):
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
        reply_markup=InlineKeyboardMarkup(buttons))

async def handle_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    media_type, media_id = query.data.split('|')
    await query.message.edit_reply_markup(reply_markup=None)
    
    endpoint = f"/{media_type}/{media_id}"
    details = await fetch_tmdb_data(endpoint)
    
    if not details:
        await query.message.reply_text("❌ Error al obtener detalles")
        return

    trailer_url = await fetch_trailer(media_type, media_id)
    
    if media_type == 'movie':
        title = details.get('title', 'Sin título')
        original_title = details.get('original_title', title)
        release_date = details.get('release_date', 'N/A')
        release_year = release_date[:4] if release_date and len(release_date) >= 4 else 'N/A'
        country = details.get('production_countries', [{}])[0].get('name', 'N/A')
        runtime = details.get('runtime', 'N/A')
        genres = ', '.join([g['name'] for g in details.get('genres', [])][:3])
        overview = details.get('overview', 'Sin descripción disponible').replace('_', '\\_').replace('*', '\\*')
        
        details_text = (
            f"🎞 *{title}* ({release_year})\n\n"
            "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n\n"
            f"📝 *Título Original:* {original_title}\n"
            f"🌍 *País:* {country}\n"
            f"⏳ *Duración:* {runtime} minutos\n"
            f"⭐ *Puntuación:* {details.get('vote_average', 'N/A')}/10\n"
            f"🎭 *Géneros:* {genres}\n\n"
            f"📖 *Sinopsis:*\n{overview}"
        )
    else:
        title = details.get('name', 'Sin título')
        original_title = details.get('original_name', title)
        first_air = details.get('first_air_date', 'N/A')
        first_year = first_air[:4] if first_air and len(first_air) >= 4 else 'N/A'
        country_code = details.get('origin_country', [''])[0]
        country = COUNTRIES.get(country_code, country_code)
        seasons = details.get('number_of_seasons', 'N/A')
        episodes = details.get('number_of_episodes', 'N/A')
        genres = ', '.join([g['name'] for g in details.get('genres', [])][:3])
        overview = details.get('overview', 'Sin descripción disponible').replace('_', '\\_').replace('*', '\\*')
        
        details_text = (
            f"📺 *{title}* ({first_year})\n\n"
            "▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️▫️\n\n"
            f"📝 *Título Original:* {original_title}\n"
            f"🌍 *País:* {country}\n"
            f"📅 *Temporadas:* {seasons}\n"
            f"🎬 *Episodios totales:* {episodes}\n"
            f"⭐ *Puntuación:* {details.get('vote_average', 'N/A')}/10\n"
            f"🎭 *Géneros:* {genres}\n\n"
            f"📖 *Sinopsis:*\n{overview}"
        )

    whatsapp_text = f"*🎬FastCopy🎬*\n\n{details_text}"
    if trailer_url:
        whatsapp_text += f"\n\n🎥 Tráiler oficial en español: {trailer_url}"
    
    whatsapp_text += "\n\n📍 Contenido disponible en español"
    whatsapp_link = f"https://wa.me/?text={quote(whatsapp_text)}"
    
    keyboard_buttons = []
    if trailer_url:
        keyboard_buttons.append([InlineKeyboardButton("🎥 Ver Tráiler ES", url=trailer_url)])
    keyboard_buttons.append([InlineKeyboardButton("📤 Compartir por WhatsApp", url=whatsapp_link)])
    
    keyboard = InlineKeyboardMarkup(keyboard_buttons)

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

        search_params = {
            "query": query,
            "include_adult": False,
            "page": 1,
            "sort_by": "popularity.desc"
        }
        
        search_data = await fetch_tmdb_data(
            f"/search/{media_type}",
            search_params
        )
        
        if not search_data or not search_data.get('results'):
            await update.message.reply_text(f"⚠️ No se encontraron resultados para: {query}")
            return

        await show_results(update.message, search_data['results'], query, media_type)

        remaining = 5 + user_searches[user_id]['granted'] - user_searches[user_id]['count']
        if remaining == 2:
            await context.bot.send_message(
                chat_id=ADMIN_ID,
                text=f"⚠️ User {user_id} tiene {remaining} búsquedas restantes"
            )

    except Exception as e:
        logger.error(f"Error en buscar_media: {str(e)}")
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
        [InlineKeyboardButton("🎬 Películas por Género", callback_data="content_type:movie"),
         InlineKeyboardButton("📺 Series por Género", callback_data="content_type:tv")],
        [InlineKeyboardButton("📺 Novelas por País", callback_data="content_type:novelas")],
        [InlineKeyboardButton("🔙 Atrás", callback_data="back_to_main")]
    ]
    
    await query.edit_message_text(
        text="🎉 Últimos 30 estrenos recientes\nSelecciona el tipo de contenido:",
        reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_content_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, content_type = query.data.split(':')
    
    if content_type == 'novelas':
        await handle_country_selection(update, context)
        return
    
    media_type = content_type
    genres = await fetch_genres(media_type)
    
    # Agregar géneros especiales
    special_genres = {'27': 'Terror'} if media_type == 'movie' else {'80': 'Policiacas'}
    combined_genres = {**special_genres, **genres}
    
    if not combined_genres:
        await query.message.reply_text("❌ Error al obtener géneros")
        return
    
    keyboard = []
    genre_items = list(combined_genres.items())
    
    # Mostrar géneros especiales primero
    for i in range(0, len(genre_items[:6]), 2):
        row = []
        for genre_id, genre_name in genre_items[i:i+2]:
            row.append(InlineKeyboardButton(genre_name, callback_data=f"genre_select:{media_type}:{genre_id}"))
        keyboard.append(row)
    
    keyboard.append([InlineKeyboardButton("🎭 Todos los Géneros", callback_data=f"genre_select:{media_type}:0")])
    keyboard.append([InlineKeyboardButton("🔙 Atrás", callback_data="releases_menu")])
    
    await query.edit_message_text(
        text=f"🎭 Selecciona un género para {'películas' if media_type == 'movie' else 'series'}:",
        reply_markup=InlineKeyboardMarkup(keyboard))

async def fetch_genres(media_type: str):
    genre_data = await fetch_tmdb_data(f"/genre/{media_type}/list")
    return {genre['id']: genre['name'] for genre in genre_data.get('genres', [])} if genre_data else {}

async def handle_country_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [
            InlineKeyboardButton("🇹🇷 Turquía", callback_data="novela_country:TR"),
            InlineKeyboardButton("🇲🇽 Mexicana", callback_data="novela_country:MX")
        ],
        [
            InlineKeyboardButton("🇨🇴 Colombiana", callback_data="novela_country:CO"),
            InlineKeyboardButton("🇨🇱 Chilena", callback_data="novela_country:CL")
        ],
        [
            InlineKeyboardButton("🇧🇷 Brasileña", callback_data="novela_country:BR"),
            InlineKeyboardButton("🌍 Cualquier país", callback_data="novela_country:ANY")
        ],
        [InlineKeyboardButton("🔙 Atrás", callback_data="releases_menu")]
    ]
    
    await query.edit_message_text(
        text="🌍 Selecciona el tipo de novelas:",
        reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_genre_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, media_type, genre_id = query.data.split(':')
    genre_id = int(genre_id)
    
    context.user_data['current_search'] = {
        'media_type': media_type,
        'genre_id': genre_id if genre_id != 0 else None
    }
    
    await process_releases_search(update, context)

async def handle_novela_country(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, country_code = query.data.split(':')
    
    context.user_data['current_search'] = {
        'media_type': 'novela',
        'country': country_code
    }
    
    await process_releases_search(update, context)

async def process_releases_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.callback_query.from_user.id)
    
    if not await check_user_limit(user_id):
        await update.callback_query.message.reply_text("⚠️ Límite de búsquedas alcanzado")
        return
    
    search_data = context.user_data['current_search']
    media_type = search_data['media_type']
    
    params = {
        "sort_by": "popularity.desc",
        "language": "es-ES",
        "page": 1
    }
    
    try:
        if media_type == 'novela':
            params.update({
                "with_genres": 10766,
                "first_air_date.gte": (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d")
            })
            
            if search_data.get('country') != 'ANY':
                params["with_origin_country"] = search_data.get('country')
            
            data = await fetch_tmdb_data("/discover/tv", params)
            results = [(item, 'tv') for item in data.get('results', [])][:30]
            
            # Fallback si no hay resultados
            if not results:
                del params['first_air_date.gte']
                data = await fetch_tmdb_data("/discover/tv", params)
                results = [(item, 'tv') for item in data.get('results', [])][:30]
        
        else:
            date_filter = "primary_release_date" if media_type == 'movie' else "first_air_date"
            params.update({
                f"{date_filter}.gte": (datetime.today() - timedelta(days=30)).strftime("%Y-%m-%d"),
                "with_genres": str(search_data.get('genre_id')) if search_data.get('genre_id') else None
            })
            
            endpoint = "/discover/movie" if media_type == 'movie' else "/discover/tv"
            data = await fetch_tmdb_data(endpoint, params)
            results = [(item, media_type) for item in data.get('results', [])][:30]
            
            # Fallback si no hay resultados
            if not results:
                params.pop(f"{date_filter}.gte", None)
                params.pop("with_genres", None)
                data = await fetch_tmdb_data(endpoint, params)
                results = [(item, media_type) for item in data.get('results', [])][:30]
        
        if not results:
            await update.callback_query.message.reply_text("❌ No se encontraron resultados")
            return
        
        # Construir título
        if media_type == 'novela':
            country_name = COUNTRIES.get(search_data.get('country', ''), '')
            title = f"📺 Novelas {country_name}" if country_name else "📺 Últimas Novelas"
        else:
            genre_name = (await fetch_genres(media_type)).get(search_data.get('genre_id', 0), 'Todos')
            title = f"{'🎬 Películas' if media_type == 'movie' else '📺 Series'} - Género: {genre_name}"
        
        await show_mixed_results(update.callback_query.message, results, title)

    except Exception as e:
        logger.error(f"Error en process_releases_search: {str(e)}")
        user_searches = load_users()
        user_searches[user_id]['count'] -= 1
        save_users(user_searches)
        await update.callback_query.message.reply_text('❌ Error procesando tu solicitud')

async def show_mixed_results(message, results, title):
    results_to_show = results[:30]
    media_groups = []
    current_media_group = []
    buttons = []
    
    for idx, (result, media_type) in enumerate(results_to_show, start=1):
        media_id = result['id']
        item_title = result.get('title') or result.get('name') or 'Sin título'
        date = result.get('release_date') or result.get('first_air_date') or ''
        year = date[:4] if len(date) >= 4 else 'N/A'
        rating = result.get('vote_average', '?')
        poster_path = result.get('poster_path', '')
        media_emoji = '🎬' if media_type == 'movie' else '📺'
        
        # Obtener país
        if media_type == 'movie':
            country = result.get('production_countries', [{}])[0].get('name', 'N/A')
        else:
            country_code = result.get('origin_country', [''])[0]
            country = COUNTRIES.get(country_code, country_code)
        
        caption = (
            f"✨ *#{idx} - {item_title}* ({year})\n\n"
            f"{media_emoji} Tipo: {'Película' if media_type == 'movie' else 'Serie'}\n"
            f"🌍 País: {country}\n"
            f"⭐ Puntuación: {rating}/10\n"
            f"🗣️ Idioma: {result.get('original_language', '').upper()}"
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
        "Selecciona para ver detalles:",
        parse_mode='Markdown',
        reply_markup=InlineKeyboardMarkup(buttons))

async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    update.message = query.message
    await start(update, context)

async def handle_random_recommendation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("🎬 Película", callback_data="random_type:movie"),
         InlineKeyboardButton("📺 Serie", callback_data="random_type:tv")],
        [InlineKeyboardButton("📺 Novela", callback_data="random_type:novela")]
    ]
    
    await query.edit_message_text(
        text="🎲 Selecciona el tipo de recomendación:",
        reply_markup=InlineKeyboardMarkup(keyboard))

async def fetch_random_media(media_type: str):
    random_page = random.randint(1, 5)
    params = {
        "sort_by": "popularity.desc",
        "page": random_page,
        "language": "es-ES",
        "primary_release_date.gte": "2008-01-01" if media_type == 'movie' else None,
        "first_air_date.gte": "2008-01-01" if media_type == 'tv' else None
    }
    endpoint = "/discover/movie" if media_type == 'movie' else "/discover/tv"
    data = await fetch_tmdb_data(endpoint, {k: v for k, v in params.items() if v is not None})
    return [(item, media_type) for item in data.get('results', [])] if data else []

async def fetch_random_novela():
    params = {
        "with_genres": 10766,
        "sort_by": "popularity.desc",
        "page": random.randint(1, 3),
        "language": "es-ES",
        "first_air_date.gte": "2008-01-01"
    }
    data = await fetch_tmdb_data("/discover/tv", params)
    return [(item, 'tv') for item in data.get('results', [])] if data else []

async def handle_random_type(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, media_type = query.data.split(':')
    
    user_id = str(query.from_user.id)
    user_searches = load_users()
    
    if not await check_user_limit(user_id):
        await query.message.reply_text("⚠️ Límite de búsquedas alcanzado")
        return
    
    try:
        if media_type == 'novela':
            results = await fetch_random_novela()
        else:
            results = await fetch_random_media(media_type)
        
        if not results:
            await query.message.reply_text("❌ No se encontraron recomendaciones")
            return
        
        selected = random.choice(results[:10])
        media_type = selected[1]
        media_id = selected[0]['id']
        details = selected[0]
        
        user_searches[user_id]['count'] += 1
        save_users(user_searches)
        
        await show_random_result(query.message, details, media_type, media_id)
        
    except Exception as e:
        logger.error(f"Error en recomendación aleatoria: {str(e)}")
        await query.message.reply_text("❌ Error al generar recomendación")

async def show_random_result(message, result, media_type, media_id):
    details = result
    trailer_url = await fetch_trailer(media_type, media_id)
    
    # Obtener géneros
    genres = []
    if media_type == 'movie':
        genre_data = await fetch_genres('movie')
        genre_ids = details.get('genre_ids', [])
        genres = [genre_data.get(g_id, '') for g_id in genre_ids[:3]]
    elif media_type in ('tv', 'novela'):
        genre_data = await fetch_genres('tv')
        genre_ids = details.get('genre_ids', [])
        genres = [genre_data.get(g_id, '') for g_id in genre_ids[:3]]
    
    genres_str = ', '.join(filter(None, genres)) or 'No especificado'

    # Obtener país
    if media_type == 'movie':
        country = details.get('production_countries', [{}])[0].get('name', 'N/A')
    else:
        country_code = details.get('origin_country', [''])[0]
        country = COUNTRIES.get(country_code, country_code)

    title = details.get('title') or details.get('name') or 'Sin título'
    date = details.get('release_date') or details.get('first_air_date') or ''
    year = date[:4] if len(date) >= 4 else 'N/A'
    rating = details.get('vote_average', 'N/A')
    overview = details.get('overview', 'Sin descripción disponible').replace('_', '\\_').replace('*', '\\*')
    
    caption = (
        f"🎲 *Recomendación Aleatoria (Post-2008)*\n\n"
        f"🎬 *Título:* {title} ({year})\n"
        f"🌍 *País:* {country}\n"
        f"⭐ *Puntuación:* {rating}/10\n"
        f"🎭 *Géneros:* {genres_str}\n\n"
        f"📖 *Sinopsis:*\n{overview}"
    )
    
    if trailer_url:
        caption += f"\n\n🎥 [Ver Tráiler]({trailer_url})"
    
    poster_path = details.get('poster_path', '')
    
    try:
        if poster_path:
            await message.reply_photo(
                photo=f"{IMAGE_BASE_URL}{poster_path}",
                caption=caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 Compartir", callback_data=f"share:{media_type}|{media_id}")]
                ])
            )
        else:
            await message.reply_text(
                caption,
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📤 Compartir", callback_data=f"share:{media_type}|{media_id}")]
                ])
            )
    except Exception as e:
        logger.error(f"Error mostrando recomendación: {str(e)}")
        await message.reply_text(caption, parse_mode='Markdown')

def main():
    application = Application.builder() \
        .token(TOKEN) \
        .post_init(post_init) \
        .build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("credito", credito))
    
    application.add_handler(CallbackQueryHandler(select_search_type, pattern=r"^search_type:"))
    application.add_handler(CallbackQueryHandler(handle_selection, pattern=r"^movie\|.+|^tv\|.+"))
    application.add_handler(CallbackQueryHandler(show_user_status, pattern=r"^user_status"))
    application.add_handler(CallbackQueryHandler(show_admin_stats, pattern=r"^admin_stats"))
    application.add_handler(CallbackQueryHandler(show_releases_menu, pattern=r"^releases_menu"))
    application.add_handler(CallbackQueryHandler(handle_content_selection, pattern=r"^content_type:(movie|tv|novelas)"))
    application.add_handler(CallbackQueryHandler(handle_genre_selection, pattern=r"^genre_select:"))
    application.add_handler(CallbackQueryHandler(handle_novela_country, pattern=r"^novela_country:"))
    application.add_handler(CallbackQueryHandler(back_to_main, pattern=r"^back_to_main"))
    application.add_handler(CallbackQueryHandler(handle_random_recommendation, pattern=r"^random_menu"))
    application.add_handler(CallbackQueryHandler(handle_random_type, pattern=r"^random_type:"))
    
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_search))

    application.run_polling()

if __name__ == '__main__':
    main()
