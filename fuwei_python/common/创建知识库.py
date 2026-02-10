import json
import types
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.lkeap.v20240522 import lkeap_client, models
from conf.config import app_config
try:
    # 实例化一个认证对象，入参需要传入腾讯云账户 SecretId 和 SecretKey，此处还需注意密钥对的保密
    # 代码泄露可能会导致 SecretId 和 SecretKey 泄露，并威胁账号下所有资源的安全性
    # 以下代码示例仅供参考，建议采用更安全的方式来使用密钥
    # 请参见：https://cloud.tencent.com/document/product/1278/85305
    # 密钥可前往官网控制台 https://console.cloud.tencent.com/cam/capi 进行获取
    print(app_config)
    cred = credential.Credential(app_config['tx_cos_secret_id'], app_config['tx_cos_secret_key'])
    # 实例化一个http选项，可选的，没有特殊需求可以跳过
    httpProfile = HttpProfile()
    httpProfile.endpoint = "lkeap.tencentcloudapi.com"

    # 实例化一个client选项，可选的，没有特殊需求可以跳过
    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile
    # 实例化要请求产品的client对象,clientProfile是可选的
    client = lkeap_client.LkeapClient(cred, "ap-guangzhou", clientProfile)

    # 实例化一个请求对象,每个接口都会对应一个request对象
    req = models.CreateKnowledgeBaseRequest()
    params = {

    }
    req.from_json_string(json.dumps(params))

    # 返回的resp是一个CreateKnowledgeBaseResponse的实例，与请求对象对应
    resp = client.CreateKnowledgeBase(req)
    # 输出json格式的字符串回包
    print(resp.to_json_string())
#{"KnowledgeBaseId": "1904172322802110464", "RequestId": "55ff734b-af2e-4a78-8104-8f54adff02f4"}
except TencentCloudSDKException as err:
    print(err)
