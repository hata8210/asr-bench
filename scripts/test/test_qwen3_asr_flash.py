import os
import dashscope
from http import HTTPStatus

dashscope.api_key = os.environ.get('OPENAI_API_KEY')
MODEL = "qwen3-asr-flash"
audio_path = os.path.abspath("data/combined.wav")
file_url = f"file://{audio_path}"

messages = [
    {"role": "user", "content": [{"audio": file_url}]}
]

print(f"Testing MultiModalConversation.call with {MODEL} and {file_url}")
response = dashscope.MultiModalConversation.call(
    model=MODEL,
    messages=messages
)

print(f"Response: {response}")
