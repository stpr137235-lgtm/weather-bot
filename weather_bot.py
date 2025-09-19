from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
import requests
import os

# Хранилище выбранных городов: user_id -> city_name
user_city = {}

from telegram import ReplyKeyboardMarkup

main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        ["🔄 Обновить прогноз", "📅 Прогноз на 3 дня"],
        ["🌐 Изменить город", "🐱🐶 Котопёсики🥰"]
    ],
    resize_keyboard=True
)

# 🔧 Вставьте сюда свои ключи
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")


# 🌤 Функция получения погоды
import requests
from datetime import datetime, timedelta
import pytz
from timezonefinder import TimezoneFinder

OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")

def get_weather(city: str) -> str:
    # --- Текущая погода ---
    current_url = f'https://api.openweathermap.org/data/2.5/weather?q={city}&appid={OPENWEATHERMAP_API_KEY}&units=metric&lang=ru'
    current_response = requests.get(current_url)

    if current_response.status_code != 200:
        return 'Город не найден🥲'

    current_data = current_response.json()

    temp = current_data['main']['temp']
    feels_like = current_data['main']['feels_like']
    pressure_hpa = current_data['main']['pressure']
    pressure_mmHg = round(pressure_hpa * 0.75006)
    weather = current_data['weather'][0]['description']
    humidity = current_data['main']['humidity']
    wind_speed = current_data['wind']['speed']

    # --- Время и часовой пояс ---
    lat = current_data['coord']['lat']
    lon = current_data['coord']['lon']

    tf = TimezoneFinder()
    timezone_str = tf.timezone_at(lat=lat, lng=lon) or 'UTC'
    tz = pytz.timezone(timezone_str)
    now = datetime.now(tz)

    time_str = now.strftime('%H:%M')
    weekday_ru = {
        'Monday': 'понедельник',
        'Tuesday': 'вторник',
        'Wednesday': 'среда',
        'Thursday': 'четверг',
        'Friday': 'пятница',
        'Saturday': 'суббота',
        'Sunday': 'воскресенье'
    }
    date_formatted = f"{weekday_ru[now.strftime('%A')]} {now.strftime('%d.%m.%Y')}"

    # --- Восход и закат ---
    sunrise = datetime.fromtimestamp(current_data['sys']['sunrise'], tz)
    sunset = datetime.fromtimestamp(current_data['sys']['sunset'], tz)
    sunrise_str = sunrise.strftime('%H:%M')
    sunset_str = sunset.strftime('%H:%M')

    # --- Прогноз на сегодня ---
    forecast_url = f'https://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OPENWEATHERMAP_API_KEY}&units=metric&lang=ru'
    forecast_response = requests.get(forecast_url)

    if forecast_response.status_code != 200:
        return 'Не удалось получить прогноз погоды😐'

    forecast_data = forecast_response.json()

    forecast_today = {
        'morning': [],
        'day': [],
        'evening': [],
        'night': []
    }

    for item in forecast_data['list']:
        dt_utc = datetime.utcfromtimestamp(item['dt']).replace(tzinfo=pytz.utc).astimezone(tz)
        forecast_date = dt_utc.date()
        hour = dt_utc.hour
        temp = round(item['main']['temp'])
        description = item['weather'][0]['description']

        # 🌅 Утро: 03:00–10:00
        if forecast_date == now.date() and 3 <= hour < 10:
            forecast_today['morning'].append((temp, description))

        # 🌤 День: 10:00–17:00
        elif forecast_date == now.date() and 10 <= hour < 17:
            forecast_today['day'].append((temp, description))

        # 🌇 Вечер: 17:00–21:00
        elif forecast_date == now.date() and 17 <= hour < 21:
            forecast_today['evening'].append((temp, description))

        # 🌃 Ночь: 21:00–23:59 сегодняшнего дня
        elif forecast_date == now.date() and 21 <= hour <= 23:
            forecast_today['night'].append((temp, description))

        # 🌃 Ночь: 00:00–03:00 следующего дня
        elif forecast_date == now.date() + timedelta(days=1) and 0 <= hour < 3:
            forecast_today['night'].append((temp, description))

    def summarize(period_data):
        if not period_data:
            return "нет данных"
        avg_temp = round(sum(t for t, _ in period_data) / len(period_data))
        common_desc = max(set(d for _, d in period_data), key=lambda d: [desc for _, desc in period_data].count(d))
        return f"{avg_temp}°C, {common_desc}"

    # Определяем текущее время (локальное)
    current_hour = now.hour

    # Готовим строки прогноза только для актуальных периодов
    forecast_parts = []
    forecast_parts.append("🕑 Прогноз на остаток дня:")

    if current_hour < 10:
        forecast_parts.append(f"🌅 Утро {summarize(forecast_today['morning'])}")
    if current_hour < 17:
        forecast_parts.append(f"🌤 День {summarize(forecast_today['day'])}")
    if current_hour < 21:
        forecast_parts.append(f"🌇 Вечер {summarize(forecast_today['evening'])}")
    if current_hour >= 21 or current_hour < 3:
        forecast_parts.append(f"🌃 Ночь {summarize(forecast_today['night'])}")

    # Объединяем всё в один текст
    forecast_text = "\n".join(forecast_parts)

    # --- Качество воздуха ---
    air_quality_url = f"http://api.openweathermap.org/data/2.5/air_pollution?lat={lat}&lon={lon}&appid={OPENWEATHERMAP_API_KEY}"
    air_response = requests.get(air_quality_url)
    air_quality_text = ""
    if air_response.status_code == 200:
        air_data = air_response.json()
        if "list" in air_data and air_data["list"]:
            pm2_5 = air_data["list"][0]["components"]["pm2_5"]
            pm10 = air_data["list"][0]["components"]["pm10"]

            def classify_air_quality(pm2_5, pm10):
                max_value = max(pm2_5, pm10)
                if max_value <= 12:
                    return "🟢 Отличное"
                elif max_value <= 35:
                    return "🟡 Хорошее"
                elif max_value <= 55:
                    return "🟠 Умеренное"
                elif max_value <= 150:
                    return "🔴 Плохое"
                else:
                    return "⚫ Опасное"

            quality = classify_air_quality(pm2_5, pm10)
            air_quality_text = f"\n🌫 Качество воздуха {quality} (PM2.5: {pm2_5} µg/m³, PM10: {pm10} µg/m³)"

    # --- Итоговый текст ---
    return (
        f"📍 {city.title()} | {weekday_ru[now.strftime('%A')].capitalize()}, {now.strftime('%d.%m')}\n"
        f"🕒 Сейчас {time_str}\n\n"
        f"🌡 {temp}°C (ощущается как {feels_like}°C🤔)\n"
        f"{WEATHER_EMOJI.get(weather.lower(), '')} {weather.capitalize()}\n"
        f"💧 {humidity}% | 🌬 {wind_speed} м/с | 🔽 {pressure_mmHg} мм\n\n"
        f"🌅 Восход в {sunrise_str} | 🌇 Закат в {sunset_str}"
        f"{air_quality_text}\n\n"
        f"{forecast_text}"
    )

from datetime import datetime, timedelta
import pytz

# Словарь: английские дни недели → в предложном падеже на русском
DAYS_RU_PREPOSITIONAL = {
    "Monday": "в понедельник",
    "Tuesday": "во вторник",
    "Wednesday": "в среду",
    "Thursday": "в четверг",
    "Friday": "в пятницу",
    "Saturday": "в субботу",
    "Sunday": "в воскресенье"
}

WEATHER_EMOJI = {
    "ясно": "☀️",
    "облачно с прояснениями": "🌤",
    "переменная облачность": "🌥",
    "небольшая облачность": "⛅️",
    "пасмурно": "☁️",
    "небольшой дождь": "🌦",
    "дождь": "🌧",
    "сильный дождь": "🌧🌧",
    "гроза": "⛈",
    "небольшой снег": "🌨",
    "снег": "❄️",
    "сильный снег": "❄️❄️",
    "туман": "🌫",
    "морось": "🌧",
    "ливень": "🌧💧",
    "шторм": "🌪",
}

def get_three_day_forecast(city_name):
    url = f"http://api.openweathermap.org/data/2.5/forecast?q={city_name}&appid={OPENWEATHERMAP_API_KEY}&units=metric&lang=ru"
    response = requests.get(url)
    if response.status_code != 200:
        return "Не удалось получить прогноз погоды 😕"

    data = response.json()
    if "city" not in data:
        return "Город не найден 😔"

    city_info = data["city"]
    timezone_offset = city_info["timezone"]  # смещение в секундах
    tz = pytz.FixedOffset(timezone_offset // 60)

    forecasts = data["list"]
    forecast_by_date = {}

    for entry in forecasts:
        dt_utc = datetime.utcfromtimestamp(entry["dt"]).replace(tzinfo=pytz.utc)
        dt_local = dt_utc.astimezone(tz)
        date_str = dt_local.strftime("%Y-%m-%d")
        hour = dt_local.hour

        # Условия времени суток
        if 3 <= hour < 10:
            period = "Утро"
        elif 10 <= hour < 17:
            period = "День"
        elif 17 <= hour < 21:
            period = "Вечер"
        else:
            period = "Ночь"

        if date_str not in forecast_by_date:
            forecast_by_date[date_str] = {}

        if period not in forecast_by_date[date_str]:
            forecast_by_date[date_str][period] = []

        forecast_by_date[date_str][period].append(entry)

    # Получаем 3 следующих дня
    today = datetime.utcnow().astimezone(tz).date()
    result = ""

    for i in range(1, 4):
        target_date = today + timedelta(days=i)
        date_str = target_date.strftime("%Y-%m-%d")
        weekday_en = target_date.strftime("%A")
        weekday_ru_prep = DAYS_RU_PREPOSITIONAL.get(weekday_en, weekday_en)
        date_display = f"{weekday_ru_prep.capitalize()} {target_date.strftime('%d.%m')}"

        result += f"\n📅 {date_display}:\n"

        if date_str not in forecast_by_date:
            result += "Нет данных\n"
            continue

        for period in ["Утро", "День", "Вечер", "Ночь"]:
            entries = forecast_by_date[date_str].get(period)
            if not entries:
                result += f"{period} — нет данных\n"
                continue

            temps = [e["main"]["temp"] for e in entries]
            descriptions = [e["weather"][0]["description"] for e in entries]
            wind_speeds = [e["wind"]["speed"] for e in entries]

            avg_temp = round(sum(temps) / len(temps))
            common_desc = max(set(descriptions), key=descriptions.count)
            emoji = WEATHER_EMOJI.get(common_desc.lower(), "")
            avg_wind = round(sum(wind_speeds) / len(wind_speeds), 1)

            result += f"{period} | {avg_temp}°C | {common_desc} | {avg_wind} м/с\n"

    return result.strip()


import random
import requests
from telegram import Update
from telegram.ext import ContextTypes


async def send_random_pet(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        choice = random.choice(["cat", "dog"])

        if choice == "cat":
            url = f"https://cataas.com/cat?{random.randint(1, 10000)}"
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=url)
        else:
            # Пробуем до 5 раз найти фото-пса
            for _ in range(100):
                response = requests.get("https://random.dog/woof.json").json()
                url = response["url"]
                if url.endswith((".jpg", ".jpeg", ".png")):
                    await context.bot.send_photo(chat_id=update.effective_chat.id, photo=url)
                    return

            # Если фото так и не нашлось
            await update.message.reply_text("Все пёсики заняты съёмками 🎬🐶 Попробуй позже.")

    except Exception:
        await update.message.reply_text("Не удалось получить котопёсика 😿🐶")


# 🛠 Обработчик команды /start
from telegram import Update
from telegram.ext import ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_first_name = update.effective_user.first_name or "друг"
    await update.message.reply_text(
        f"Привет, {user_first_name}! 👋\n"
        "Напиши название города, и я пришлю тебе погоду 🌤",
        reply_markup=main_keyboard
    )

# 📩 Обработчик текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    # Кнопка "Изменить город"
    if text == "🌐 Изменить город":
        user_city[user_id] = None
        await update.message.reply_text("Введите новый город:")
        return

    # Кнопка "Обновить прогноз"
    if text == "🔄 Обновить прогноз":
        city = user_city.get(user_id)
        if not city:
            await update.message.reply_text("Сначала введите город 🥹")
            return
        weather_info = get_weather(city)
        await update.message.reply_text(weather_info, reply_markup=main_keyboard)
        return

    # Кнопка "Прогноз на 3 дня"
    if text == "📅 Прогноз на 3 дня":
        city = user_city.get(user_id)
        if not city:
            await update.message.reply_text("Сначала введите город 🥹", reply_markup=main_keyboard)
            return

        forecast = get_three_day_forecast(city)
        await update.message.reply_text(forecast, reply_markup=main_keyboard)
        return

    # Кнопка "Котейки"
    if text == "🐱🐶 Котопёсики🥰":
        await send_random_pet(update, context)
        return

    # Ввод города пользователем
    city = text
    user_city[user_id] = city
    weather_info = get_weather(city)
    await update.message.reply_text(weather_info, reply_markup=main_keyboard)


# 🚀 Основная функция запуска бота
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен...")
    app.run_polling()


if __name__ == '__main__':
    main()