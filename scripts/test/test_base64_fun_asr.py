import dashscope
import base64
from dashscope.audio.asr import Transcription
from http import HTTPStatus
import os

dashscope.api_key = os.environ.get('OPENAI_API_KEY')

audio_path = "data/hello_world_female2.wav"

with open(audio_path, 'rb') as f:
    audio_data = f.read()
    base64_audio = base64.b64encode(audio_data).decode('utf-8')
    data_uri = f"data:audio/wav;base64,{base64_audio}"

print(f"Testing Transcription.async_call with model='fun-asr' and Base64 Data URI")
task_response = Transcription.async_call(
    model='fun-asr',
    file_urls=[data_uri]
)

if task_response.status_code == HTTPStatus.OK:
    print(f'Task submitted, task_id: {task_response.output.task_id}')
    transcription_response = Transcription.wait(task=task_response.output.task_id)
    if transcription_response.status_code == HTTPStatus.OK:
        print("Success!")
        print(transcription_response.output)
    else:
        print(f"Wait failed: {transcription_response.code} - {transcription_response.message}")
else:
    print(f"Submission failed: {task_response.code} - {task_response.message}")
