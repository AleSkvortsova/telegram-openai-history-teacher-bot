import sys
import types

# Создаем фейковый модуль imghdr перед импортом telegram
class FakeImghdr:
    @staticmethod
    def what(filename, h=None):
        # Минимальная реализация для обхода ошибки
        return 'jpeg'

# Подменяем модуль imghdr
sys.modules['imghdr'] = types.ModuleType('imghdr')
sys.modules['imghdr'].what = FakeImghdr.what


import logging
import asyncio
from openai import OpenAI
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, ContextTypes, filters

from src import OPENAI_API_KEY, ASSISTANT_ID, TELEGRAM_TOKEN

# Инициализируем клиент OpenAI
client = OpenAI(api_key=OPENAI_API_KEY)

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Словарь для хранения диалогов пользователей
user_threads = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я бот-помощник по подготовке тестовых заданий по истории.\n"
        "Напиши какое задание подготовить, открытого или закрытого типа.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_message = update.message.text
    user_id = update.message.from_user.id

    status_msg = await update.message.reply_text("Обрабатываю запрос...")

    try:
        # Получаем или создаем thread для пользователя
        if user_id in user_threads:
            thread_id = user_threads[user_id]
        else:
            thread = client.beta.threads.create()
            thread_id = thread.id
            user_threads[user_id] = thread_id

        # Отправляем сообщение ассистенту
        client.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=user_message
        )

        # Запускаем обработку ассистентом
        run = client.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        # Ждем завершения обработки
        while run.status in ("queued", "in_progress"):
            await asyncio.sleep(0.5)
            run = client.beta.threads.runs.retrieve(
                thread_id=thread_id,
                run_id=run.id
            )

        # Получаем ответ
        messages = client.beta.threads.messages.list(thread_id=thread_id)

        # Извлекаем текст ответа ассистента
        response_texts = []
        for msg in reversed(messages.data):
            if msg.role == "assistant" and msg.content:
                for content in msg.content:
                    if hasattr(content, 'text') and hasattr(content.text, 'value'):
                        response_texts.append(content.text.value)
        
        response = "\n".join(response_texts) if response_texts else "Нет ответа от ассистента."
        
        # Обрезаем длинные сообщения (Telegram ограничение 4096 символов)
        if len(response) > 4000:
            response = response[:4000] + "..."
            
        await status_msg.edit_text(response)

    except Exception as e:
        logger.error(f"Ошибка: {e}", exc_info=True)
        await status_msg.edit_text("Ошибка при обработке запроса. Попробуйте позже.")

async def post_init(application: Application):
    """Функция, вызываемая после инициализации бота"""
    await application.bot.set_my_commands([
        ("start", "Запустить бота"),
        ("help", "Помощь")
    ])

def main():
    try:
        # Создаем приложение для версии 21.x
        application = Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
        
        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        
        print("✅ Бот запущен!")
        
        # Запускаем бота
        application.run_polling(
            drop_pending_updates=True,
            allowed_updates=Update.ALL_TYPES
        )
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}", exc_info=True)
        print(f"❌ Ошибка: {e}")

if __name__ == "__main__":
    main()