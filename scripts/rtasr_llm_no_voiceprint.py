# -*- encoding:utf-8 -*-
import hashlib
import hmac
import base64
import json
import time
import threading
import urllib.parse
import uuid
from websocket import create_connection
import datetime
import argparse
import os
import sys

# ==================== 静态配置区域 ====================
# 使用经过验证的账号信息
APP_ID = os.environ.get('IFLYTEK_APP_ID')
ACCESS_KEY_ID = os.environ.get('IFLYTEK_API_KEY')
ACCESS_KEY_SECRET = os.environ.get('IFLYTEK_API_SECRET')

# 全局配置
FIXED_PARAMS = {
    "audio_encode": "pcm_s16le",
    "lang": "autodialect",
    "samplerate": "16000",
    "role_type": "2",  # 开启说话人分离，更适合面试场景
}

AUDIO_FRAME_SIZE = 1280  # 每帧音频字节数
FRAME_INTERVAL_MS = 40    # 每帧发送间隔
# ======================================================

# 强制不使用代理，避免网络干扰
os.environ['no_proxy'] = '*'

class RTASRClient():
    def __init__(self, audio_path):
        self.app_id = APP_ID
        self.access_key_id = ACCESS_KEY_ID
        self.access_key_secret = ACCESS_KEY_SECRET
        self.audio_path = audio_path
        self.base_ws_url = "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1"
        self.ws = None
        self.is_connected = False
        self.recv_thread = None
        self.session_id = None
        self.is_sending_audio = False
        self.full_result = [] # 用于存储所有的识别结果块
        self.final_received = False # 标记是否收到 ls=true

    def _get_audio_file_size(self):
        try:
            return os.path.getsize(self.audio_path)
        except Exception as e:
            print(f"【获取文件大小失败】{str(e)}")
            return 0

    def _generate_auth_params(self):
        auth_params = {
            "accessKeyId": self.access_key_id,
            "appId": self.app_id,
            "uuid": uuid.uuid4().hex,
            "utc": self._get_utc_time(),
            **FIXED_PARAMS
        }
        sorted_params = dict(sorted([(k, v) for k, v in auth_params.items() if v is not None and str(v).strip() != ""]))
        base_str = "&".join([f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}" for k, v in sorted_params.items()])
        signature = hmac.new(self.access_key_secret.encode("utf-8"), base_str.encode("utf-8"), hashlib.sha1).digest()
        auth_params["signature"] = base64.b64encode(signature).decode("utf-8")
        return auth_params

    def _get_utc_time(self):
        beijing_tz = datetime.timezone(datetime.timedelta(hours=8))
        now = datetime.datetime.now(beijing_tz)
        return now.strftime("%Y-%m-%dT%H:%M:%S%z")

    def connect(self):
        try:
            auth_params = self._generate_auth_params()
            params_str = urllib.parse.urlencode(auth_params)
            full_ws_url = f"{self.base_ws_url}?{params_str}"

            # 明确指定不使用代理
            self.ws = create_connection(full_ws_url, timeout=15, enable_multithread=True)
            self.is_connected = True

            self.recv_thread = threading.Thread(target=self._recv_msg, daemon=True)
            self.recv_thread.start()
            return True
        except Exception as e:
            print(f"【连接失败】{str(e)}")
            return False

    def _recv_msg(self):
        while self.is_connected and self.ws:
            try:
                msg = self.ws.recv()
                if not msg:
                    break
                if isinstance(msg, str):
                    msg_json = json.loads(msg)
                    if msg_json.get('msg_type') == 'action':
                        action = msg_json.get('data', {}).get('action')
                        if action == 'error':
                            print(f"\n【服务错误】{msg_json}")
                        if 'sessionId' in msg_json.get('data', {}):
                            self.session_id = msg_json['data']['sessionId']
                    elif msg_json.get('msg_type') == 'result':
                        data = msg_json.get('data', {})
                        # 解析转写文字
                        if data.get('cn', {}).get('st', {}).get('type') == '0': # 0 为确定性结果
                            rt_list = data['cn']['st']['rt']
                            text = ""
                            for rt_item in rt_list:
                                for ws_item in rt_item['ws']:
                                    for cw_item in ws_item['cw']:
                                        text += cw_item['w']
                            
                            if text:
                                self.full_result.append(text)
                                # 实时输出，方便查看进度
                                sys.stdout.write(text)
                                sys.stdout.flush()
                        
                        # 检查是否为最后一帧
                        if data.get('ls') is True:
                            self.final_received = True
                            self.is_connected = False # 通知主线程结束
            except Exception as e:
                break

    def send_audio(self):
        if not self.is_connected: return False
        self.is_sending_audio = True
        
        speed_factor = 1.0 
        
        try:
            with open(self.audio_path, "rb") as f:
                header = f.read(44)
                # 跳过WAV头
                if not (header.startswith(b'RIFF') and b'WAVE' in header):
                    f.seek(0)

                frame_index = 0
                start_time = time.time() * 1000
                
                while True:
                    chunk = f.read(AUDIO_FRAME_SIZE)
                    if not chunk: break

                    expected_time = start_time + (frame_index * FRAME_INTERVAL_MS / speed_factor)
                    diff = expected_time - (time.time() * 1000)
                    if diff > 0:
                        time.sleep(diff / 1000)

                    self.ws.send_binary(chunk)
                    frame_index += 1

                # 发送结束标记
                end_msg = {"end": True}
                if self.session_id: end_msg["sessionId"] = self.session_id
                self.ws.send(json.dumps(end_msg))
            return True
        except Exception as e:
            print(f"\n【发送异常】{str(e)}")
            return False
        finally:
            self.is_sending_audio = False

    def close(self):
        self.is_connected = False
        if self.ws: 
            try:
                self.ws.close()
            except:
                pass

    def get_full_text(self):
        return "".join(self.full_result)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="讯飞实时语音转写大模型版工具")
    parser.add_argument("--wav_file", type=str, required=True, help="待识别的音频文件路径 (.wav)")
    args = parser.parse_args()

    if not os.path.exists(args.wav_file):
        print(f"错误: 文件 {args.wav_file} 不存在")
        sys.exit(1)

    client = RTASRClient(args.wav_file)
    try:
        if client.connect():
            # 开始上传音频
            client.send_audio()
            
            # 等待所有识别结果返回，直到收到 ls=true 或超时
            max_wait = 120 # 对于长音频，大模型可能需要一些处理时间
            start_wait = time.time()
            while not client.final_received and (time.time() - start_wait < max_wait):
                time.sleep(0.5)
            
            # 识别完成后换行
            print("\n")
            
            # 打印最终完整的识别结果
            full_text = client.get_full_text()
            if full_text:
                print("==================== 完整识别结果 ====================")
                print(full_text)
                print("======================================================")
            else:
                print("未能获取到识别结果，请检查网络或音频文件。")
    finally:
        client.close()
