# -*- coding: utf-8 -*-
import base64
import hmac
import json
import os
import random
import string
import requests
import urllib.parse
import datetime
import warnings

# 忽略SSL验证警告
warnings.filterwarnings("ignore", category=requests.packages.urllib3.exceptions.InsecureRequestWarning)

# ==================== 账号配置 ====================
APP_ID = os.environ.get('IFLYTEK_APP_ID')
API_KEY = os.environ.get('IFLYTEK_API_KEY')
API_SECRET = os.environ.get('IFLYTEK_API_SECRET')


AUDIO_FILE_PATH = "data/combined.wav"
# ======================================================

LFASR_HOST = "https://office-api-personal-dx.iflyaisol.com"
REGISTER_FUNC = "/res/feature/v1/register"

class VoiceprintRegisterDebug:
    def __init__(self):
        self.appid = APP_ID
        self.apikey = API_KEY
        self.apisecret = API_SECRET

    def _get_utc_time(self):
        """生成严格对齐文档的时间格式：2025-09-04T15:38:07+0800"""
        now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))
        # 显式构造，确保没有微秒，且时区格式为 +0800
        return now.strftime("%Y-%m-%dT%H:%M:%S") + "+0800"

    def _generate_signature(self, params):
        """生成签名：严格按照字典序和全量URL编码"""
        # 1. 过滤空值并排序
        sorted_params = sorted(params.items(), key=lambda x: x[0])
        
        # 2. 构造 baseString，注意 safe='' 确保所有特殊字符被转义
        base_parts = []
        for k, v in sorted_params:
            encoded_key = urllib.parse.quote(str(k), safe='')
            encoded_value = urllib.parse.quote(str(v), safe='')
            base_parts.append(f"{encoded_key}={encoded_value}")
        
        base_string = "&".join(base_parts)
        
        # 3. HMAC-SHA1
        hmac_obj = hmac.new(
            self.apisecret.encode("utf-8"),
            base_string.encode("utf-8"),
            digestmod="sha1"
        )
        return base64.b64encode(hmac_obj.digest()).decode("utf-8")

    def run(self):
        # 1. 准备请求参数
        date_time = self._get_utc_time()
        signature_random = ''.join(random.choices(string.ascii_letters + string.digits, k=16))
        
        url_params = {
            "appId": self.appid,
            "accessKeyId": self.apikey,
            "dateTime": date_time,
            "signatureRandom": signature_random,
        }

        # 2. 生成签名
        signature = self._generate_signature(url_params)

        # 3. 构造请求 URL (Query Params 也要编码)
        encoded_query = "&".join([
            f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}" 
            for k, v in url_params.items()
        ])
        full_url = f"{LFASR_HOST}{REGISTER_FUNC}?{encoded_query}"

        # 4. 准备 Body (只需音频，不需要文字)
        if not os.path.exists(AUDIO_FILE_PATH):
            print(f"【错误】文件不存在：{AUDIO_FILE_PATH}")
            return

        with open(AUDIO_FILE_PATH, 'rb') as f:
            audio_base64 = base64.b64encode(f.read()).decode('utf-8')

        headers = {
            "Content-Type": "application/json",
            "signature": signature
        }
        body = {
            "audio_data": audio_base64,
            "audio_type": "raw",
            "uid": "test_user_001"
        }

        print(f"【尝试注册】URL: {full_url[:80]}...")
        try:
            resp = requests.post(full_url, headers=headers, json=body, timeout=30, verify=False)
            print(f"【状态码】{resp.status_code}")
            result = resp.json()
            
            if result.get("code") == "000000":
                data = json.loads(result.get("data", "{}"))
                print("\n" + "★"*20)
                print("【注册成功！】")
                print(f"您的声纹特征ID (feature_id): {data.get('feature_id')}")
                print("★"*20)
            else:
                print(f"【注册失败】错误码：{result.get('code')}")
                print(f"错误描述：{result.get('desc')}")
                print(f"完整返回：{result}")
        except Exception as e:
            print(f"【网络异常】{str(e)}")

if __name__ == "__main__":
    demo = VoiceprintRegisterDebug()
    demo.run()
