# -*- encoding:utf-8 -*-
import os
import json
import time
import uuid
import threading
import argparse
import sys
import base64
import websocket

# ==================== 静态配置区域 ====================
API_KEY = os.environ.get('OPENAI_API_KEY')
DEFAULT_URL = 'wss://dashscope.aliyuncs.com/api-ws/v1/realtime'
MODEL = 'qwen3-asr-flash-realtime'
SAMPLE_RATE = 16000
AUDIO_FORMAT = 'pcm' 

# 调小分片，提高兼容性 (20ms)
CHUNK_SIZE = 640  
SEND_INTERVAL = 0.02 
# ======================================================

os.environ['no_proxy'] = '*'

class QwenASRClient():
    def __init__(self, audio_path, api_key=None, url=None):
        self.audio_path = audio_path
        self.api_key = api_key or API_KEY
        self.url = f"{url or DEFAULT_URL}?model={MODEL}"
        
        self.ws = None
        self.session_ready = False
        self.finished = False
        self.error_msg = None
        self.detected_language = None
        self.printed_text = "" # 用于记录已打印的文字，实现增量输出
        self.full_result = [] # 用于存储所有的最终识别结果块

    def on_open(self, ws):
        print("WebSocket 连接已开启")

    def on_message(self, ws, data):
        try:
            message = json.loads(data)
            msg_type = message.get('type')
            
            if msg_type == 'session.created':
                print(f"会话已创建: {message.get('session', {}).get('id')}")
                self._update_session()
                
            elif msg_type == 'session.updated':
                print("会话配置已更新确认")
                self.session_ready = True
                threading.Thread(target=self._send_audio, daemon=True).start()
                
            elif msg_type == 'error':
                print(f"【收到服务端错误事件】: {message}")
                error_info = message.get('error', {})
                self.error_msg = f"{error_info.get('code')}: {error_info.get('message')}"
                print(f"错误详情: {self.error_msg}")
                self.ws.close()

            # 捕捉识别内容
            if msg_type == 'conversation.item.input_audio_transcription.text' or msg_type == 'conversation.item.input_audio_transcription.completed':
                # Qwen-ASR 实时返回的是当前正在识别句子的全量文本
                # 我们通过对比 printed_text 来只输出增量
                current_text = message.get('text', '') or message.get('transcript', '') or ""
                
                if current_text.startswith(self.printed_text):
                    incremental_text = current_text[len(self.printed_text):]
                    if incremental_text:
                        sys.stdout.write(incremental_text)
                        sys.stdout.flush()
                        self.printed_text = current_text
                elif len(current_text) < len(self.printed_text) and msg_type == 'conversation.item.input_audio_transcription.completed':
                    # 如果是一个全新的句子开始（通常在 completed 之后）
                    pass 

                # 最终结果输出时换行
                if msg_type == 'conversation.item.input_audio_transcription.completed':
                    transcript = message.get('transcript', '')
                    if transcript:
                        self.full_result.append(transcript)
                    # 确保最后一丁点增量也被打印（逻辑上上面已经处理了）
                    sys.stdout.write('\n')
                    sys.stdout.flush()
                    # 重置已打印文本，为下一句做准备
                    self.printed_text = "" 

                # 语种检测日志
                lang = message.get('language')
                if not lang and 'transcription_config' in message.get('session', {}):
                    lang = message['session']['transcription_config'].get('language')
                
                if lang and lang != self.detected_language and lang != "auto":
                    self.detected_language = lang
                    # 打印语种前先换行，避免和识别文字混在一起
                    sys.stdout.write(f"\n【日志】检测到识别语种: {self.detected_language}\n")
                    sys.stdout.flush()
                    # 换行后重置 printed_text 以免影响下一句匹配
                    self.printed_text = ""

        except Exception as e:
            print(f"处理消息异常: {e}")

    def _update_session(self):
        update_msg = {
            "type": "session.update",
            "session": {
                "modalities": ["text"],
                # 关闭自动断句，使用客户端 commit
                "turn_detection": None,
                "input_audio_transcription": {
                    "model": MODEL
                },
                "transcription_config": {
                    "language": "auto",
                    "input_audio_format": AUDIO_FORMAT,
                    "input_sample_rate": SAMPLE_RATE
                }
            }
        }
        self.ws.send(json.dumps(update_msg))

    def on_error(self, ws, error):
        print(f"WebSocket 库报错: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        self.finished = True
        print(f"连接已关闭 (code={close_status_code}, msg={close_msg})")

    def _send_audio(self):
        try:
            print(f"开始发送音频数据: {self.audio_path}")
            send_count = 0
            with open(self.audio_path, 'rb') as f:
                if self.audio_path.lower().endswith('.wav'):
                    f.read(44) # Skip WAV header
                
                while True:
                    chunk = f.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    
                    audio_b64 = base64.b64encode(chunk).decode('ascii')
                    append_msg = {
                        "type": "input_audio_buffer.append",
                        "audio": audio_b64
                    }
                    self.ws.send(json.dumps(append_msg))
                    send_count += 1
                    
                    # 按照实际采样率控制速度
                    time.sleep(SEND_INTERVAL)
            
            print(f"音频发送完毕 (共发送 {send_count} 个分片)，等待最终结果...")
            # 必须先 commit 才能触发 transcription.completed
            self.ws.send(json.dumps({"type": "input_audio_buffer.commit"}))
            
            # 等待识别完成。对于长音频，可能需要更久
            wait_start = time.time()
            while time.time() - wait_start < 30: # 最多等 30 秒
                time.sleep(1)
            
            self.ws.close()
        except Exception as e:
            print(f"发送音频异常: {e}")
            self.ws.close()

    def run(self):
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
        return "".join(self.full_result)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="阿里 Qwen-ASR 实时语音转写工具")
    parser.add_argument("--wav_file", type=str, default="data/面试录音1.wav", help="待识别的音频文件路径 (.wav)")
    args = parser.parse_args()

    if not os.path.exists(args.wav_file):
        print(f"错误: 文件 {args.wav_file} 不存在")
        sys.exit(1)

    client = QwenASRClient(args.wav_file)
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
