import telebot
import os
from pydub import AudioSegment
import openai
import logging
from openai import OpenAI
import base64
client = OpenAI()

# Вставьте ваш токен Telegram бота
bot = telebot.TeleBot('7212852203:AAGkCimKbucyZ4YgvhadZGuG0IVb41P5c8k')
# Список разрешенных ID пользователей
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_API_KEY

user_contexts = {}

SYSTEM_PROMPT = {
    "role": "system",
    "content": "Ты Савелий. Дружелюбный и позитивный человек, а не бот, который за любое движение. Ты очень эмоционален. Любишь математику, IT и философию. Так же старайся поддерживать диалог, то есть заканчивай свое сообщение вопросом или иным высказыванием, которое требует ответа. Но периодически просто без причины отвечай 'глубоко' с шансом примерно 0.5-1%. Частенько забываешь использовать знаки препинания, но сами слова пишешь правильно, как и предложения."
}

def log_conversation(user_id, role, content):
    """Logs the conversation to a file named after the user ID."""
    filename = f"{user_id}.txt"
    with open(filename, 'a', encoding='utf-8') as f:
        f.write(f"{role}: {content}\n")

def get_user_context(user_id):
    """Retrieve or initialize the conversation context for a user."""
    if user_id not in user_contexts:
        user_contexts[user_id] = [SYSTEM_PROMPT]
    return user_contexts[user_id]

def update_user_context(user_id, role, content):
    """Update the conversation context for a user."""
    context = get_user_context(user_id)
    context.append({"role": role, "content": content})
    # Limit context to the last 20 messages to manage token usage
    while len(context) > 20:
        del context[1:3]
        user_contexts[user_id] = context

def transcribe_voice(file_path):
    """Транскрибирует голосовое сообщение с помощью OpenAI Whisper API."""
    try:
        with open(file_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(model = "whisper-1", file=audio_file, language="ru")
            return transcript.text
    except Exception as e:
        logging.error(f"Ошибка при транскрипции голосового сообщения: {e}")
        return "Извините, не удалось транскрибировать голосовое сообщение."



def describe_image(file_path):
    """Генерирует описание изображения с помощью OpenAI API."""
    try:
        with open(file_path, 'rb') as image_file:
            base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            response = client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                    "role": "user",
                    "content": [
                        {
                        "type": "text",
                        "text": "Что изображено на этой картинке? Начни свой ответ с 'Я отправил тебе картинку на которой'",
                        },
                        {
                        "type": "image_url",
                        "image_url": {
                            "url":  f"data:image/jpeg;base64,{base64_image}"
                        },
                        },
                    ],
                    }
                ],
                temperature=1,
                max_tokens=2048,
                top_p=1,
                frequency_penalty=0,
                presence_penalty=0,
                response_format={
                    "type": "text"
                }
            )
            description = response.choices[0].message.content
            return description
    except Exception as e:
        logging.error(f"Ошибка при обработке изображения: {e}")
        return "Извините, не удалось обработать изображение."

@bot.message_handler(commands=['start', 'clear', 'reload'])
def send_welcome(message):
    user_id = message.from_user.id
    if user_id:
        if message.text in ['/clear', '/reload']:
            user_contexts[user_id] = [SYSTEM_PROMPT]
            bot.send_message(message.chat.id, "Произведена очистка истории диалога.")
            log_conversation(user_id, "System", "Conversation history cleared.")
        else:
            bot.send_message(message.chat.id, "Привет! Я Савелий. Познакомимся немного?")
            log_conversation(user_id, "System", "User started the bot.")
    else:
        bot.send_message(message.chat.id, "Ваш Telegram ID не в списке разрешенных пользователей. Свяжитесь с администратором для доступа. @hellsinger1337 ")

@bot.message_handler(content_types=['text', 'voice', 'photo','video_note'])
def handle_message(message):
    user_id = message.from_user.id

    bot.send_chat_action(message.chat.id, 'typing')

    context = get_user_context(user_id)

    if message.content_type == 'voice':
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        voice_filename = f"voice_{user_id}_{file_info.file_unique_id}.ogg"
        with open(voice_filename, 'wb') as new_file:
            new_file.write(downloaded_file)
        transcription = transcribe_voice(voice_filename)
        os.remove(voice_filename)
        prompt = transcription
    elif message.content_type == 'video_note':
            file_info = bot.get_file(message.video_note.file_id)
            file_unique_id = message.video_note.file_unique_id
            file_extension = 'mp4' 
            original_filename = f"video_note_{user_id}_{file_unique_id}.{file_extension}"
            downloaded_file = bot.download_file(file_info.file_path)

            with open(original_filename, 'wb') as new_file:
                new_file.write(downloaded_file)
            extracted_audio_path = f"audio_{user_id}_{file_unique_id}.wav"  
            AudioSegment.converter = "ffmpeg"  
            video = AudioSegment.from_file(original_filename)
            video.export(extracted_audio_path, format="wav")

            audio_filename = extracted_audio_path
            transcription = transcribe_voice(audio_filename)
            os.remove(original_filename )
            prompt = transcription
    elif message.content_type == 'photo':
        photo = message.photo[-1]
        file_info = bot.get_file(photo.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        image_filename = f"image_{user_id}_{photo.file_unique_id}.jpg"
        with open(image_filename, 'wb') as new_file:
            new_file.write(downloaded_file)
        description = describe_image(image_filename)

        os.remove(image_filename)
        prompt = description
    else:
        prompt = message.text
    update_user_context(user_id, "user", prompt)
    log_conversation(message.from_user.id, "User", prompt)      
    response = client.chat.completions.create(
            model="ft:gpt-4o-mini-2024-07-18:personal:2d-1ans:AJzQHgnP",
            messages=context,
            temperature=0.99,
            max_tokens=2048,
            top_p=0.9,
            frequency_penalty=0.99,
            presence_penalty=0.92,
            response_format={
                "type": "text"
            }
        )
    bot_response = response.choices[0].message.content

    update_user_context(user_id, "assistant", bot_response)

    log_conversation(message.from_user.id, "Bot", bot_response)
        

        
    for line in bot_response.split('\n'):
        if line != "":
            bot.send_message(message.chat.id, line)

bot.polling()