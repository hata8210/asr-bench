# -*- encoding:utf-8 -*-
import os
import json
import time
import uuid
import threading
import argparse
import sys
import websocket

# ==================== 静态配置区域 ====================
# 如果没有设置环境变量 OPENAI_API_KEY，可以在这里设置
API_KEY = os.environ.get('OPENAI_API_KEY')

# 默认 WebSocket 地址
# 如果是专有业务空间，请修改为 wss://{WorkspaceId}.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference/
DEFAULT_URL = 'wss://dashscope.aliyuncs.com/api-ws/v1/inference/'

# 模型配置
MODEL = 'fun-asr-realtime'
SAMPLE_RATE = 16000
AUDIO_FORMAT = 'wav'

CHUNK_SIZE = 3200  # 100ms @ 16kHz 16bit 单声道
SEND_INTERVAL = 0.1 # 100ms
# ======================================================

# 强制不使用代理，避免网络干扰
os.environ['no_proxy'] = '*'

class FunASRClient():
    def __init__(self, audio_path, api_key=None, url=None):
        self.audio_path = audio_path
        self.api_key = api_key or API_KEY
        self.url = url or DEFAULT_URL
        self.task_id = uuid.uuid4().hex[:32]
        
        self.ws = None
        self.task_started = False
        self.task_finished = False
        self.full_result = []
        self.last_sentence = ""
        self.error_msg = None

    def on_open(self, ws):
        # 发送 run-task 指令
        run_task_message = {
            'header': {
                'action': 'run-task',
                'task_id': self.task_id,
                'streaming': 'duplex'
            },
            'payload': {
                'task_group': 'audio',
                'task': 'asr',
                'function': 'recognition',
                'model': MODEL,
                'parameters': {
                    'sample_rate': SAMPLE_RATE,
                    'format': AUDIO_FORMAT
                },
                'input': {}
            }
        }
        ws.send(json.dumps(run_task_message))

    def on_message(self, ws, data):
        message = json.loads(data)
        event = message['header']['event']
        
        if event == 'task-started':
            self.task_started = True
            # 开启发送音频的线程
            threading.Thread(target=self._send_audio, daemon=True).start()
            
        elif event == 'result-generated':
            payload = message.get('payload', {})
            output = payload.get('output', {})
            sentence = output.get('sentence', {})
            text = sentence.get('text', '')
            
            if text:
                # 阿里 ASR 的中间结果会包含之前已经确认的部分，所以我们需要处理一下输出
                # 这里采用简单的实时输出逻辑：如果 sentence_end 为 True，表示一句话结束
                is_end = sentence.get('sentence_end', False)
                
                # 为了模拟 rtasr_llm_no_voiceprint.py 的实时输出效果
                # 我们只打印自上次以来新增的部分，或者在 sentence_end 时换行
                # 但阿里返回的是整句，所以这里简单处理：打印整句并在 sentence_end 时保存
                
                # 简单实现：如果是中间结果，我们用 \r 覆盖打印（由于 sys.stdout.write 不方便 \r）
                # 或者参考原脚本：实时输出 text
                # 注意：fun-asr 的 text 是增量的整句，所以直接打印会重复
                
                # 这里我们记录已经打印出的部分，或者只在 sentence_end 时输出
                # 为了更好的体验，我们采用增量打印
                new_part = text[len(self.last_sentence):]
                if new_part:
                    sys.stdout.write(new_part)
                    sys.stdout.flush()
                    self.last_sentence = text
                
                if is_end:
                    self.full_result.append(text)
                    self.last_sentence = "" # 重置，下一句从头开始
                    # sys.stdout.write('\n') # 换行
                    # sys.stdout.flush()

        elif event == 'task-finished':
            self.task_finished = True
            self.ws.close()
            
        elif event == 'task-failed':
            self.error_msg = message['header'].get('error_message')
            self.task_finished = True
            self.ws.close()

    def on_error(self, ws, error):
        if not self.task_finished:
            self.error_msg = str(error)
        self.task_finished = True

    def on_close(self, ws, close_status_code, close_msg):
        self.task_finished = True

    def _send_audio(self):
        try:
            with open(self.audio_path, 'rb') as f:
                # 跳过 WAV 头（阿里 ASR 格式设为 wav 时通常需要包含头或者不包含头取决于具体实现，
                # 但其 demo 是一次性读取或按块读取包含头的文件）
                # 这里我们保持和原文件一致，尝试读取并发送
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    self.ws.send(chunk, opcode=websocket.ABNF.OPCODE_BINARY)
                    time.sleep(SEND_INTERVAL)
            
            # 发送 finish-task 指令
            finish_task_message = {
                'header': {
                    'action': 'finish-task',
                    'task_id': self.task_id,
                    'streaming': 'duplex'
                },
                'payload': {
                    'input': {}
                }
            }
            self.ws.send(json.dumps(finish_task_message))
        except Exception as e:
            self.error_msg = f"发送音频错误: {str(e)}"
            self.ws.close()

    def run(self):
        if not self.api_key:
            print("错误: 未提供 DASHSCOPE_API_KEY，请设置环境变量或在代码中硬编码。")
            return
            
        self.ws = websocket.WebSocketApp(
            self.url,
            header={'Authorization': f'bearer {self.api_key}'},
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        self.ws.run_forever()

    def get_full_text(self):
        # 加上最后一句话（如果还没结束）
        results = list(self.full_result)
        if self.last_sentence:
            results.append(self.last_sentence)
        return "".join(results)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="阿里 FunASR 实时语音转写工具")
    parser.add_argument("--wav_file", type=str, default="data/面试录音1.wav", help="待识别的音频文件路径 (.wav)")
    args = parser.parse_args()

    if not os.path.exists(args.wav_file):
        print(f"错误: 文件 {args.wav_file} 不存在")
        sys.exit(1)

    client = FunASRClient(args.wav_file)
    
    print(f"正在启动 FunASR 识别: {args.wav_file}")
    client.run()
    
    if client.error_msg:
        print(f"\n【识别失败】{client.error_msg}")
    else:
        print("\n")
        full_text = client.get_full_text()
        if full_text:
            print("==================== 完整识别结果 ====================")
            print(full_text)
            print("======================================================")
        else:
            print("未能获取到识别结果，请检查网络或音频文件。")
