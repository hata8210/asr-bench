# -*- coding: utf-8 -*-
import base64
import hmac
import json
import os
import time
import random
import string
import requests
import urllib.parse
import datetime
import warnings
import wave  # 使用Python内置的wave模块，无需额外安装
import orderResult
# from pydub import AudioSegment
# import pydub

# 忽略SSL验证警告（生产环境建议开启验证）
warnings.filterwarnings("ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

# 讯飞API基础配置
LFASR_HOST = "https://office-api-personal-dx.iflyaisol.com"
register_func = "/res/feature/v1/register"
update_func = "/res/feature/v1/update"
delete_func= "/res/feature/v1/delete"


class XfyunAsrClient:
    def __init__(self, appid, access_key_id, access_key_secret):
        self.appid = appid
        self.access_key_id = access_key_id
        self.access_key_secret = access_key_secret
        # self.audio_file_path = self._check_audio_path(audio_file_path)
        # self.audio_duration = self._get_audio_duration_ms()  # 获取音频时长（毫秒，整数）
        # self.order_id = None
        self.signature_random = self._generate_random_str()
        self.last_base_string = ""  # 签名原始串（编码后）
        self.last_signature = ""    # 最终签名
        self.upload_url = ""        # 最终生成的请求URL

    def _check_audio_path(self, path):
        if not os.path.exists(path):
            raise FileNotFoundError(f"音频文件不存在：{path}")
        # 校验是否为WAV文件
        # if not path.lower().endswith(".wav"):
        #     raise ValueError(f"当前代码仅支持pcm/wav格式音频，您的文件格式为：{os.path.splitext(path)[1]}")
        return os.path.abspath(path)

    def _generate_random_str(self, length=16):
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def _get_local_time_with_tz(self):
        """生成带时区偏移的本地时间（格式：yyyy-MM-dd'T'HH:mm:ss±HHmm）"""
        local_now = datetime.datetime.now()
        tz_offset = local_now.astimezone().strftime('%z')  # 输出格式：+0800 或 -0500
        return f"{local_now.strftime('%Y-%m-%dT%H:%M:%S')}{tz_offset}"

    def _get_audio_duration_ms(self):
        """
        获取音频时长（毫秒，整数），支持pcm/WAV（内置wave模块）和MP3（基于FFmpeg）
        """
        try:
            # 处理WAV格式（保留原逻辑，无需依赖外部工具）
            if self.audio_file_path.lower().endswith('.wav'):
                with wave.open(self.audio_file_path, 'rb') as audio_file:
                    n_frames = audio_file.getnframes()  # 总帧数
                    sample_rate = audio_file.getframerate()  # 采样率（Hz）
                    duration_ms = int(round(n_frames / sample_rate * 1000))  # 转换为毫秒
                    return duration_ms
                    
            # 处理MP3格式（基于ffmpeg-python）
            elif self.audio_file_path.lower().endswith('.mp3'):
                # 导入ffmpeg库（需提前安装）
                import ffmpeg
                # 调用FFmpeg探测音频文件信息
                probe = ffmpeg.probe(self.audio_file_path)
                # 提取音频流信息（排除视频流）
                audio_stream = next(stream for stream in probe['streams'] if stream['codec_type'] == 'audio')
                # 获取时长（秒）并转换为毫秒（整数）
                duration_seconds = float(audio_stream['duration'])
                duration_ms = int(round(duration_seconds * 1000))
                return duration_ms
                
            # 不支持的格式
            else:
                raise Exception(f"不支持的音频格式！仅支持WAV/MP3，当前文件：{self.audio_file_path}")
                
        except Exception as e:
            # 捕获所有异常并明确提示
            raise Exception(f"获取音频时长失败：{str(e)}\n提示：若为MP3，请确认FFmpeg已安装并配置环境变量")


    def generate_signature(self, params):
        """生成签名（根据文档要求：对key和value都进行url encode后生成baseString）"""
        # 排除signature参数，按参数名自然排序（与Java TreeMap一致）
        sign_params = {k: v for k, v in params.items() if k != "signature"}
        sorted_params = sorted(sign_params.items(), key=lambda x: x[0])
        
        # 构建baseString：对key和value都进行URL编码
        base_parts = []
        for k, v in sorted_params:
            if v is not None and str(v).strip() != "":
                encoded_key = urllib.parse.quote(k, safe='')  # 参数名编码
                encoded_value = urllib.parse.quote(str(v), safe='')  # 参数值编码
                base_parts.append(f"{encoded_key}={encoded_value}")
        
        self.last_base_string = "&".join(base_parts)
        
        # HMAC-SHA1加密 + Base64编码
        hmac_obj = hmac.new(
            self.access_key_secret.encode("utf-8"),
            self.last_base_string.encode("utf-8"),
            digestmod="sha1"
        )
        self.last_signature = base64.b64encode(hmac_obj.digest()).decode("utf-8")
        return self.last_signature
    
    def register(self,audio_path):
        date_time = self._get_local_time_with_tz()              # 带时区的本地时间
        url_params = {
            "appId": self.appid,
            "accessKeyId": self.access_key_id,
            "dateTime": date_time,
            "signatureRandom": self.signature_random,

        }

        # 3. 生成签名（duration参数参与签名计算）
        signature = self.generate_signature(url_params)
        if not signature:
            raise Exception("签名生成失败，结果为空")

        # 4. 构建请求头
        headers = {
            "Content-Type": "application/json",
            "signature": signature,

        }

        # 5. 构建最终请求URL
        encoded_params = []
        for k, v in url_params.items():
            encoded_key = urllib.parse.quote(k, safe='')
            encoded_v = urllib.parse.quote(str(v), safe='')
            encoded_params.append(f"{encoded_key}={encoded_v}")
        self.upload_url = f"{LFASR_HOST}{register_func}?{'&'.join(encoded_params)}"

        body = {
            "audio_data": self.audio_to_base64(audio_path),
            "audio_type":"raw" ,  # 按照音频格式进行调整, raw 即为 pcm/wav 格式音频
            "uid":"uidwhf"
        }

        try:
            
            response = requests.post(
                url=self.upload_url,
                headers=headers,
                json= body,
                timeout=30,
                verify=False  # 测试环境关闭SSL验证
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"上传请求网络失败：{str(e)}")

        # 7. 解析响应结果
        try:
            result = json.loads(response.text)
            print("注册结果：",result)
        except json.JSONDecodeError:
            raise Exception(f"API返回非JSON数据：{response.text}")
        
        return result

    #更新音频
    def update(self,feature_id,audio_apdate_path):
        date_time = self._get_local_time_with_tz()              # 带时区的本地时间
        url_params = {
            "appId": self.appid,
            "accessKeyId": self.access_key_id,
            "dateTime": date_time,
            "signatureRandom": self.signature_random,

        }

        # 3. 生成签名（duration参数参与签名计算）
        signature = self.generate_signature(url_params)
        if not signature:
            raise Exception("签名生成失败，结果为空")

        # 4. 构建请求头
        headers = {
            "Content-Type": "application/json",
            "signature": signature
        }

        # 5. 构建最终请求URL
        encoded_params = []
        for k, v in url_params.items():
            encoded_key = urllib.parse.quote(k, safe='')
            encoded_v = urllib.parse.quote(str(v), safe='')
            encoded_params.append(f"{encoded_key}={encoded_v}")
        self.upload_url = f"{LFASR_HOST}{update_func}?{'&'.join(encoded_params)}"

        body = {
            "audio_data": self.audio_to_base64(audio_apdate_path),
            "feature_id":feature_id,   # 按照音频格式进行调整, raw 即为 pcm格式音频
            "audio_type":"raw"
        }

        try:
            
            response = requests.post(
                url=self.upload_url,
                headers=headers,
                json= body,
                timeout=30,
                verify=False  # 测试环境关闭SSL验证
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"上传请求网络失败：{str(e)}")

        # 7. 解析响应结果
        try:
            result = json.loads(response.text)
            print("更新结果：",result)
        except json.JSONDecodeError:
            raise Exception(f"API返回非JSON数据：{response.text}")
        
        return result


    def delete(self,feature_ids):
        date_time = self._get_local_time_with_tz()              # 带时区的本地时间
        url_params = {
            "appId": self.appid,
            "accessKeyId": self.access_key_id,
            "dateTime": date_time,
            "signatureRandom": self.signature_random,

        }

        # 3. 生成签名（duration参数参与签名计算）
        signature = self.generate_signature(url_params)
        if not signature:
            raise Exception("签名生成失败，结果为空")

        # 4. 构建请求头
        headers = {
            "Content-Type": "application/json",
            "signature": signature
        }

        # 5. 构建最终请求URL
        encoded_params = []
        for k, v in url_params.items():
            encoded_key = urllib.parse.quote(k, safe='')
            encoded_v = urllib.parse.quote(str(v), safe='')
            encoded_params.append(f"{encoded_key}={encoded_v}")
        self.upload_url = f"{LFASR_HOST}{delete_func}?{'&'.join(encoded_params)}"

        body = {
            "feature_ids":feature_ids,   # 按照音频格式进行调整, raw 即为 pcm/wav 格式音频
        }
        print(body)

        try:
            
            response = requests.post(
                url=self.upload_url,
                headers=headers,
                json= body,
                timeout=30,
                verify=False  # 测试环境关闭SSL验证
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise Exception(f"上传请求网络失败：{str(e)}")

        # 7. 解析响应结果
        try:
            result = json.loads(response.text)
            print("更新结果：",result)
        except json.JSONDecodeError:
            raise Exception(f"API返回非JSON数据：{response.text}")
        
        return result



    def audio_to_base64(self,audio_file_path):
        """
        将音频文件转换为Base64编码字符串
        
        参数:
            audio_file_path: 音频文件的路径
            
        返回:
            成功: Base64编码字符串
            失败: None
        """
        try:
            # 检查文件是否存在
            if not os.path.exists(audio_file_path):
                print(f"错误: 文件 '{audio_file_path}' 不存在")
                return None
                
            # 检查文件是否为音频文件（简单判断）
            valid_extensions = ['.wav', '.mp3', '.ogg', '.flac', '.aac']
            file_ext = os.path.splitext(audio_file_path)[1].lower()
            if file_ext not in valid_extensions:
                print(f"警告: 文件 '{audio_file_path}' 可能不是有效的音频文件")
            
            # 读取文件并进行Base64编码
            with open(audio_file_path, 'rb') as audio_file:
                # 读取二进制数据
                audio_data = audio_file.read()
                # 进行Base64编码
                base64_encoded = base64.b64encode(audio_data).decode('utf-8')
                return base64_encoded
                
        except Exception as e:
            print(f"转换音频文件到Base64时出错: {str(e)}")
            return None
        

if __name__ == "__main__":
    # -------------------------- 请替换为你的真实参数 --------------------------
    XFYUN_APPID = "XXXXXXXX"  # 你的appId
    XFYUN_ACCESS_KEY_ID = "XXXXXXXXXXXXXXXXXXXXXXXX"  # 你的apiKey
    XFYUN_ACCESS_KEY_SECRET = "XXXXXXXXXXXXXXXXXXXXXXXX"  # 你的apiSecret
    AUDIO_FILE = "python\\audio\\声纹分离注册.wav"  # 音频文件路径
    # --------------------------------------------------------------------------

            # 初始化客户端并执行完整转写流程
    asr_client = XfyunAsrClient(
        appid=XFYUN_APPID,
        access_key_id=XFYUN_ACCESS_KEY_ID,
        access_key_secret=XFYUN_ACCESS_KEY_SECRET
    )
    # 注册音频
    final_result = asr_client.register(AUDIO_FILE)


    # 更新音频
    # final_result = asr_client.update("20250918230019446ygDeLdBoiC08RTKG",AUDIO_FILE)



    #删除声纹
    # final_result = asr_client.delete(['20250918231248655AqK5GyNtf898q2Eg'])
