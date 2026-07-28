import dashscope
import base64
from dashscope.audio.asr import Transcription
from http import HTTPStatus
import os
import sys

# ==================== 配置区域 ====================
# 使用环境变量中的 API Key，如果没有则使用脚本中的默认值
dashscope.api_key = os.environ.get('OPENAI_API_KEY')

# 待测试的本地音频文件路径
# 注意：Base64 方式适用于较小的音频文件（建议 10MB 以内）
DEFAULT_AUDIO_PATH = "data/hello_world_female2.wav"
# ======================================================

def transcribe_local_file(file_path):
    """
    使用 Base64 Data URI 方式调用 fun-asr 模型识别本地文件
    """
    if not os.path.exists(file_path):
        print(f"错误: 文件 {file_path} 不存在")
        return

    print(f"正在读取并编码本地文件: {file_path}")
    
    try:
        # 读取音频并转为 Base64
        with open(file_path, 'rb') as f:
            audio_data = f.read()
            # 检查文件大小，Base64 编码会增加体积，对于超过 10MB 的文件建议上传到 OSS
            if len(audio_data) > 10 * 1024 * 1024:
                print("警告: 文件较大，Base64 编码可能导致请求失败。对于大文件，建议先上传到您的阿里云 OSS。")
            
            base64_audio = base64.b64encode(audio_data).decode('utf-8')
            # 构造 Data URI，假设是 wav 格式
            # 阿里 ASR 支持多种格式，通常 wav/mp3/m4a 都可以
            ext = os.path.splitext(file_path)[1].lower().replace('.', '')
            if ext == 'm4a':
                mime_type = 'audio/x-m4a'
            else:
                mime_type = f'audio/{ext}'
            
            data_uri = f"data:{mime_type};base64,{base64_audio}"

        print(f"正在提交 ASR 任务 (模型: fun-asr)...")
        # 调用异步接口
        task_response = Transcription.async_call(
            model='fun-asr',
            file_urls=[data_uri]
        )

        if task_response.status_code == HTTPStatus.OK:
            print(f'任务已提交, task_id: {task_response.output.task_id}')
            
            # 等待任务完成
            print("正在等待识别结果 (轮询中)...")
            transcription_response = Transcription.wait(task=task_response.output.task_id)
            
            if transcription_response.status_code == HTTPStatus.OK:
                print("\n==================== 识别成功 ====================")
                # transcription_response.output 包含了识别结果详情
                # 实际上完整的文本在 transcription_url 指向的 JSON 文件中
                results = transcription_response.output.get('results', [])
                for index, res in enumerate(results):
                    trans_url = res.get('transcription_url')
                    if trans_url:
                        print(f"文件 {index+1} 识别结果下载地址: {trans_url}")
                
                # 打印出 API 返回的摘要信息
                print(f"Request ID: {transcription_response.request_id}")
                print(f"任务状态: {transcription_response.output.task_status}")
                print("==================================================\n")
            else:
                print(f"任务执行失败: {transcription_response.code} - {transcription_response.message}")
        else:
            print(f"任务提交失败: {task_response.code} - {task_response.message}")
            
    except Exception as e:
        print(f"发生异常: {str(e)}")

if __name__ == "__main__":
    # 支持从命令行参数传入文件路径
    audio_to_test = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_AUDIO_PATH
    transcribe_local_file(audio_to_test)
