import dashscope
from dashscope.audio.asr import Transcription
from http import HTTPStatus
import os

dashscope.api_key = os.environ.get('OPENAI_API_KEY')

file_url = 'https://dashscope.oss-cn-beijing.aliyuncs.com/samples/audio/paraformer/hello_world_female2.wav'

print(f"Testing Transcription.async_call with {file_url}")
task_response = Transcription.async_call(
    model='fun-asr',
    file_urls=[file_url]
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
