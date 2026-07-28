# -*- encoding:utf-8 -*-
import hashlib
import hmac
import base64
import json
import time
import threading
import urllib.parse
import logging
import uuid
from websocket import create_connection, WebSocketException
import websocket
import datetime

# ==================== 静态配置区域 ====================
# 使用经过验证的账号信息
APP_ID = os.environ.get('IFLYTEK_APP_ID')
ACCESS_KEY_ID = os.environ.get('IFLYTEK_API_KEY')
ACCESS_KEY_SECRET = os.environ.get('IFLYTEK_API_SECRET')

AUDIO_FILE_PATH = "data/面试录音1.wav"

# 全局配置：去掉声纹 ID，仅保留基础转写配置
FIXED_PARAMS = {
    "audio_encode": "pcm_s16le",
    "lang": "autodialect",
    "samplerate": "16000",
    "role_type": "2",  # 开启说话人分离，更适合面试场景
}

AUDIO_FRAME_SIZE = 1280  # 每帧音频字节数（16k采样率、16bit位深、40ms）
FRAME_INTERVAL_MS = 40    # 每帧发送间隔（毫秒）
# ======================================================

class RTASRClient():
    def __init__(self):
        self.app_id = APP_ID
        self.access_key_id = ACCESS_KEY_ID
        self.access_key_secret = ACCESS_KEY_SECRET
        self.audio_path = AUDIO_FILE_PATH
        self.base_ws_url = "wss://office-api-ast-dx.iflyaisol.com/ast/communicate/v1"
        self.ws = None
        self.is_connected = False
        self.recv_thread = None
        self.session_id = None
        self.is_sending_audio = False
        self.audio_file_size = 0
        self.pending_text = "" # 用于聚合显示的缓冲区

    def _get_audio_file_size(self):
        try:
            with open(self.audio_path, "rb") as f:
                f.seek(0, 2)
                return f.tell()
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
            print(f"【连接信息】建立基础转写连接...")

            self.ws = create_connection(full_ws_url, timeout=15, enable_multithread=True)
            self.is_connected = True
            print("【连接成功】握手完成")

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
                    print("【接收线程】收到空消息，连接可能已关闭")
                    break
                if isinstance(msg, str):
                    msg_json = json.loads(msg)
                    if msg_json.get('msg_type') == 'action':
                        action = msg_json.get('data', {}).get('action')
                        if action == 'error':
                            print(f"【服务错误】{msg_json}")
                        else:
                            print(f"【服务状态】{action}")
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
                                self.pending_text += text
                                # 当缓冲区超过 100 字或遇到句末标点时输出
                                if len(self.pending_text) >= 100 or text[-1] in '。？！?.!':
                                    print(f"【最终识别】{self.pending_text[:100]}")
                                    self.pending_text = self.pending_text[100:]
                        
                        # 检查是否为最后一帧
                        if data.get('ls') is True:
                            if self.pending_text:
                                print(f"【最终识别】{self.pending_text}")
                                self.pending_text = ""
                            print("【服务提示】收到结束标记 (ls=true)")
                            self.is_connected = False # 通知主线程结束
            except Exception as e:
                print(f"【接收异常】{str(e)}")
                break

    def send_audio(self):
        if not self.is_connected: return False
        self.is_sending_audio = True
        self.audio_file_size = self._get_audio_file_size()
        
        # 建议倍速：1.0 倍（实时速度）
        speed_factor = 1.0
        
        try:
            with open(self.audio_path, "rb") as f:
                header = f.read(44)
                if header.startswith(b'RIFF') and b'WAVE' in header:
                    print("【音频信息】检测到 WAV 头部，已跳过 44 字节")
                else:
                    f.seek(0)

                frame_index = 0
                start_time = time.time() * 1000
                total_frames = self.audio_file_size // AUDIO_FRAME_SIZE
                print(f"【开始发送】音频大小：{self.audio_file_size}字节，采用 {speed_factor}x 倍速发送...")

                while True:
                    chunk = f.read(AUDIO_FRAME_SIZE)
                    if not chunk: break

                    # 计算在 speed_factor 倍速下，当前帧应该在什么时间点发送
                    expected_time = start_time + (frame_index * FRAME_INTERVAL_MS / speed_factor)
                    diff = expected_time - (time.time() * 1000)
                    if diff > 0:
                        time.sleep(diff / 1000)

                    self.ws.send_binary(chunk)
                    frame_index += 1
                    
                    if frame_index % 100 == 0:
                        progress = (frame_index / total_frames) * 100
                        print(f"【发送进度】已上传: {progress:.1f}%", end='\r')

                print(f"\n【发送结束】所有数据已上传 (共 {frame_index} 帧)，等待最终结果...")
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
        if self.is_connected:
            self.is_connected = False
            if self.ws: self.ws.close()

if __name__ == "__main__":
    client = RTASRClient()
    try:
        if client.connect():
            client.send_audio()
            # 循环等待，直到接收线程收到 ls=true 或超时（发送完后最多等 60 秒）
            max_wait = 60
            start_wait = time.time()
            while client.is_connected and (time.time() - start_wait < max_wait):
                time.sleep(0.5)
            if client.is_connected:
                print("【等待超时】未能在 60 秒内收到结束标记")
    finally:
        client.close()
        print("【程序结束】")
