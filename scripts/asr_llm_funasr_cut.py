# -*- encoding:utf-8 -*-
import os
import argparse
import sys
import time
import json
import logging
import base64
import requests
import tempfile
from http import HTTPStatus
import dashscope
from dashscope.audio.asr import Transcription
from pydub import AudioSegment

# 启用调试日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ==================== 静态配置区域 ====================
API_KEY = os.environ.get('DASHSCOPE_API_KEY', "sk-ade44c50b24d49dabbcdde7ae960c66e")
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
    def __init__(self, audio_path, cut_size=5, window_size=10):
        self.audio_path = audio_path
        self.cut_size = cut_size
        self.window_size = window_size
        self.full_result = []

    def transcribe(self):
        print(f"正在启动切片识别 (Transcription 异步模式): {self.audio_path}")
        print(f"参数设置: cut_size={self.cut_size}s, window_size={self.window_size}s")
        
        if not os.path.exists(self.audio_path):
            print(f"错误: 文件 {self.audio_path} 不存在")
            return False

        try:
            # 加载音频
            audio = AudioSegment.from_file(self.audio_path)
            duration_sec = len(audio) / 1000.0
            print(f"音频总时长: {duration_sec:.2f} 秒")

            # 计算循环次数
            num_steps = int((duration_sec + self.cut_size - 0.001) // self.cut_size)
            
            for i in range(num_steps):
                current_end = (i + 1) * self.cut_size
                current_start = max(0, current_end - self.window_size)
                
                # 确保 end 不超过总时长
                current_end = min(current_end, duration_sec)
                
                print(f"\n--- 正在处理切片 [{i+1}/{num_steps}]: {current_start:.1f}s - {current_end:.1f}s ---")
                
                # 提取切片
                chunk = audio[current_start * 1000 : current_end * 1000]
                
                # 保存为临时文件
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tf:
                    temp_chunk_path = tf.name
                    chunk.export(temp_chunk_path, format="wav")
                
                try:
                    # 识别当前切片
                    chunk_text = self._transcribe_chunk(temp_chunk_path, offset_ms=current_start * 1000)
                    if chunk_text:
                        self.full_result.append(chunk_text)
                finally:
                    # 删除临时文件
                    if os.path.exists(temp_chunk_path):
                        os.remove(temp_chunk_path)

            return True

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"发生异常: {str(e)}")
            return False

    def _transcribe_chunk(self, chunk_path, offset_ms):
        """识别单个音频块"""
        try:
            with open(chunk_path, 'rb') as f:
                audio_data = f.read()
                base64_audio = base64.b64encode(audio_data).decode('utf-8')
                
                ext = os.path.splitext(chunk_path)[1].lower().replace('.', '')
                mime_type = f'audio/{ext}'
                data_uri = f"data:{mime_type};base64,{base64_audio}"

            task_response = Transcription.async_call(
                model=MODEL,
                file_urls=[data_uri],
                diarization_enabled=True,
                language_hints=['zh', 'yue', 'en']
            )

            if task_response.status_code == HTTPStatus.OK:
                task_id = task_response.output.task_id
                
                # 记录轮询等待时间
                start_poll_time = time.time()
                print(f"任务已提交 (task_id: {task_id}), 开始轮询...")
                
                transcription_response = Transcription.wait(task=task_id)
                
                wait_duration = time.time() - start_poll_time
                print(f"任务完成, 轮询等待耗时: {wait_duration:.2f}s")
                
                if transcription_response.status_code == HTTPStatus.OK:
                    results = transcription_response.output.get('results', [])
                    if results and results[0].get('subtask_status') == 'SUCCEEDED':
                        trans_url = results[0].get('transcription_url')
                        if trans_url:
                            res_response = requests.get(trans_url)
                            if res_response.status_code == 200:
                                res_data = res_response.json()
                                transcripts = res_data.get('transcripts', [])
                                if transcripts:
                                    sentences = transcripts[0].get('sentences', [])
                                    
                                    print("\n-------------------- 本次窗口识别结果 --------------------")
                                    current_sentences_text = []
                                    for s in sentences:
                                        speaker = s.get('speaker_id')
                                        stext = s.get('text', '')
                                        # 计算相对于原始音频的时间
                                        start = s.get('begin_time', 0) + offset_ms
                                        end = s.get('end_time', 0) + offset_ms
                                        
                                        time_str = f"[{format_ms(start)} --> {format_ms(end)}]"
                                        if speaker is not None:
                                            print(f"{time_str} [Speaker {speaker}] {stext}")
                                        else:
                                            print(f"{time_str} {stext}")
                                        current_sentences_text.append(stext)
                                    print("----------------------------------------------------------\n")
                                    
                                    return " ".join(current_sentences_text)
            return None
        except Exception as e:
            print(f"切片识别异常: {str(e)}")
            return None

    def get_full_text(self):
        # 注意：由于滑动窗口会导致内容重叠，这里的 full_text 仅作为每一步识别结果的简单罗列
        return "\n".join(self.full_result)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="阿里 非实时语音转写工具 (切片滑动窗口模式)")
    parser.add_argument("--wav_file", type=str, default="data/面试录音1.wav", help="待识别的音频文件路径 (.wav)")
    parser.add_argument("--cut_size", type=int, default=5, help="每次切割的步长 (秒)")
    parser.add_argument("--window_size", type=int, default=10, help="每次识别包含的窗口长度 (秒)")
    args = parser.parse_args()

    client = FunASRNonRealTimeClient(args.wav_file, cut_size=args.cut_size, window_size=args.window_size)
    
    start_time = time.time()
    if client.transcribe():
        end_time = time.time()
        print(f"\n总耗时: {end_time - start_time:.2f} 秒")
        
        # 由于是滑动窗口，完整结果可能包含重复信息，这里仅按步骤展示
        # full_text = client.get_full_text()
        # print("==================== 识别结果汇总 ====================")
        # print(full_text)
        # print("======================================================")
    else:
        sys.exit(1)
