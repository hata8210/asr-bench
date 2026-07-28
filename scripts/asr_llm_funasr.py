# -*- encoding:utf-8 -*-
import os
import argparse
import sys
import time
import json
import logging
import base64
import requests
from http import HTTPStatus
import dashscope
from dashscope.audio.asr import Transcription

# 启用调试日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 静态配置区域 ====================
API_KEY = os.environ.get('OPENAI_API_KEY')
dashscope.api_key = API_KEY

# 使用 test_fun_asr.py 中的模型
MODEL = 'fun-asr'

# ======================================================

def format_ms(ms):
    """将毫秒转换为 MM:SS.mmm 格式"""
    seconds = int(ms / 1000)
    minutes = seconds // 60
    remaining_seconds = seconds % 60
    milliseconds = int(ms % 1000)
    return f"{minutes:02d}:{remaining_seconds:02d}.{milliseconds:03d}"

class FunASRNonRealTimeClient():
    def __init__(self, audio_path):
        self.audio_path = audio_path
        self.full_result = ""

    def transcribe(self):
        print(f"正在启动非实时识别 (Transcription 异步模式): {self.audio_path}")
        
        if not os.path.exists(self.audio_path):
            print(f"错误: 文件 {self.audio_path} 不存在")
            return False

        try:
            # 1. 编码音频文件为 Base64 Data URI (参考 test_fun_asr.py)
            with open(self.audio_path, 'rb') as f:
                audio_data = f.read()
                base64_audio = base64.b64encode(audio_data).decode('utf-8')
                
                ext = os.path.splitext(self.audio_path)[1].lower().replace('.', '')
                if ext == 'm4a':
                    mime_type = 'audio/x-m4a'
                else:
                    mime_type = f'audio/{ext}'
                
                data_uri = f"data:{mime_type};base64,{base64_audio}"

            print(f"正在提交 ASR 任务 (模型: {MODEL})...")
            # 2. 调用异步接口
            task_response = Transcription.async_call(
                model=MODEL,
                file_urls=[data_uri],
                diarization_enabled=True,
                language_hints=['zh', 'yue', 'en']  # 恢复语种提示
            )

            if task_response.status_code == HTTPStatus.OK:
                task_id = task_response.output.task_id
                print(f"任务已提交, task_id: {task_id}")
                
                # 3. 等待任务完成 (轮询)
                print("正在等待识别结果 (轮询中)...")
                transcription_response = Transcription.wait(task=task_id)
                
                if transcription_response.status_code == HTTPStatus.OK:
                    print(f"识别任务完成")
                    
                    results = transcription_response.output.get('results', [])
                    if results and results[0].get('subtask_status') == 'SUCCEEDED':
                        trans_url = results[0].get('transcription_url')
                        if trans_url:
                            print(f"正在下载并解析识别结果: {trans_url}")
                            # 4. 获取 JSON 结果详情
                            res_response = requests.get(trans_url)
                            if res_response.status_code == 200:
                                res_data = res_response.json()
                                
                                # 解析 transcripts
                                transcripts = res_data.get('transcripts', [])
                                properties = res_data.get('properties', {})
                                if transcripts:
                                    # 提取全文
                                    self.full_result = transcripts[0].get('text', '')
                                    
                                    print("\n==================== 识别详情 ====================")
                                    
                                    # 尝试从多个位置获取语种
                                    detected_lang = (
                                        transcripts[0].get('language') or 
                                        properties.get('language') or 
                                        res_data.get('language') or
                                        transcription_response.output.get('language')
                                    )
                                    
                                    if detected_lang:
                                        print(f"【语种检测】: {detected_lang}")
                                        print("--------------------------------------------------")

                                    # 提取句子详情并打印 (包含时间轴)
                                    sentences = transcripts[0].get('sentences', [])
                                    for s in sentences:
                                        speaker = s.get('speaker_id')
                                        stext = s.get('text', '')
                                        start = s.get('begin_time', 0)
                                        end = s.get('end_time', 0)
                                        
                                        time_str = f"[{format_ms(start)} --> {format_ms(end)}]"
                                        
                                        if speaker is not None:
                                            print(f"{time_str} [Speaker {speaker}] {stext}")
                                        else:
                                            print(f"{time_str} {stext}")
                                    print("==================================================\n")
                                    return True
                                else:
                                    print("错误: 识别结果中未找到文本内容")
                            else:
                                print(f"错误: 无法下载结果文件, HTTP {res_response.status_code}")
                        else:
                            print("错误: 识别结果中缺失 transcription_url")
                    else:
                        subtask_err = results[0].get('message') if results else "未知错误"
                        print(f"子任务失败: {subtask_err}")
                else:
                    print(f"任务执行失败: {transcription_response.code} - {transcription_response.message}")
            else:
                print(f"任务提交失败: {task_response.code} - {task_response.message}")

            return False

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"发生异常: {str(e)}")
            return False

    def get_full_text(self):
        return self.full_result

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="阿里 非实时语音转写工具 (Transcription 异步模式)")
    parser.add_argument("--wav_file", type=str, default="data/面试录音1.wav", help="待识别的音频文件路径 (.wav)")
    args = parser.parse_args()

    client = FunASRNonRealTimeClient(args.wav_file)
    
    start_time = time.time()
    if client.transcribe():
        end_time = time.time()
        print(f"总耗时: {end_time - start_time:.2f} 秒")
        
        full_text = client.get_full_text()
        if full_text:
            print("==================== 完整识别结果 ====================")
            print(full_text)
            print("======================================================")
    else:
        sys.exit(1)

