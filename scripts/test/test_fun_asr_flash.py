import dashscope
from http import HTTPStatus
import os
import json

# 使用环境变量中的 API Key，如果没有则使用脚本中的默认值
dashscope.api_key = os.environ.get('OPENAI_API_KEY')

# 本地文件路径，使用绝对路径并加上 file:// 前缀
# dashscope.MultiModalConversation 接口支持 file:// 协议自动上传本地文件
audio_path = os.path.abspath("data/combined.wav")
file_url = f"file://{audio_path}"

# 注意：对于本地文件直接提交，建议使用同步接口 fun-asr-flash-2026-06-15
# 这样 SDK 会自动处理上传逻辑，且用法与 qwen3-asr-flash 脚本一致
MODEL = 'fun-asr-flash-2026-06-15'

print(f"Testing {MODEL} with {file_url}")

messages = [
    {
        "role": "user",
        "content": [
            {"audio": file_url}
        ]
    }
]

# 调用同步识别接口
response = dashscope.MultiModalConversation.call(
    model=MODEL,
    messages=messages,
    format='wav',        # 明确指定格式
    sample_rate=16000    # 明确指定采样率
)

if response.status_code == HTTPStatus.OK:
    print("Success!")
    print(json.dumps(response, indent=4, ensure_ascii=False))
else:
    print(f"Failed: {response.code} - {response.message}")
    print(f"Request ID: {response.request_id}")
