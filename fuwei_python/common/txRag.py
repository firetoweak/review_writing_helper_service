import json
import types
from tencentcloud.common import credential
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.lkeap.v20240522 import lkeap_client, models
from conf.config import app_config

class txRag():

    cred = credential.Credential(app_config['tx_secret_id'], app_config['tx_secret_key'])
    # 实例化一个http选项，可选的，没有特殊需求可以跳过
    httpProfile = HttpProfile()
    httpProfile.endpoint = "lkeap.tencentcloudapi.com"
    clientProfile = ClientProfile()
    clientProfile.httpProfile = httpProfile
    # 实例化要请求产品的client对象,clientProfile是可选的
    client = lkeap_client.LkeapClient(cred, "ap-guangzhou", clientProfile)
    docType = {"0":"1904174881804215232","1":"1904174881804215233"}
    docTypeName = {"0":"缺陷","1":"需求"}
    # 实例化一个请求对象,每个接口都会对应一个request对象
    @staticmethod
    def uploadDoc(FileUrl,ext:str,FileName,type:str):
        req = models.UploadDocRequest()
        FileType = ext.replace(".","").upper()
        FileName = FileName+ext
        params = {
            "KnowledgeBaseId": app_config['tx_knowledge_base_id'],
            "FileName": FileName,
            "FileType": FileType,
            "FileUrl": FileUrl,
            "AttributeLabels": [
                {
                    "AttributeId":app_config['attribute_id'],
                    "LabelIds":[txRag.docType[type]]
                }
            ]
        }
        print(params)
        req.from_json_string(json.dumps(params))
        resp = txRag.client.UploadDoc(req)
        return resp.DocId

    @staticmethod
    def delDoc(DocId):
        req = models.DeleteDocsRequest()
        params = {
            "KnowledgeBaseId": app_config['tx_knowledge_base_id'],
            "DocIds": [DocId]
        }
        req.from_json_string(json.dumps(params))

        # 返回的resp是一个DeleteDocsResponse的实例，与请求对象对应
        resp = txRag.client.DeleteDocs(req)
    @staticmethod
    def searchDocContent(type="-1"):
        req = models.RetrieveKnowledgeRequest()
        params = {
            "KnowledgeBaseId": app_config['tx_knowledge_base_id'],
            "Query": "讨论结果是什么",
        }
        if type in txRag.docTypeName:
            params['AttributeLabels'] = {
                "Name": "type",
                "Values": [txRag.docTypeName[type]]
            }
        req.from_json_string(json.dumps(params))
        # 返回的resp是一个RetrieveKnowledgeResponse的实例，与请求对象对应
        resp = txRag.client.RetrieveKnowledge(req)
        if resp.Records==None:
            return ""
        else:
            return resp.Records[0].Content