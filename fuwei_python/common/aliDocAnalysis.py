from common.aliOss import aliOss
from alibabacloud_docmind_api20220711.client import Client as docmind_api20220711Client
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_docmind_api20220711 import models as docmind_api20220711_models
from alibabacloud_tea_util.client import Client as UtilClient
from alibabacloud_credentials.client import Client as CredClient
from conf.config import app_config
import os

class aliDocAnalysis(aliOss):
    config = open_api_models.Config(
        # 通过credentials获取配置中的AccessKey ID
        access_key_id=app_config['ali_access_key'],
        # 通过credentials获取配置中的AccessKey Secret
        access_key_secret=app_config['ali_access_key_secret'],
    )
    # 访问的域名
    config.endpoint = f'docmind-api.cn-hangzhou.aliyuncs.com'
    config.bucket = app_config['ali_bucket']
    client = docmind_api20220711Client(config)
    @staticmethod
    def SubmitDocParserJob(local_file):
        key, url = aliDocAnalysis.uploadSignDoc(local_file)
        fileName = os.path.basename(local_file)
        fileExtension = os.path.splitext(fileName)[1][1:].lower()
        request = docmind_api20220711_models.SubmitDocParserJobRequest(
            # file_url : 文件url地址
            file_url=url,
            # file_name ：文件名称。名称必须包含文件类型
            file_name=fileName,
            # file_name_extension : 文件后缀格式。与文件名二选一
            file_name_extension= fileExtension
        )
        try:
            # 复制代码运行请自行打印 API 的返回值
            response = aliDocAnalysis.client.submit_doc_parser_job(request)
            # API返回值格式层级为 body -> data -> 具体属性。可根据业务需要打印相应的结果。如下示例为打印返回的业务id格式
            # 获取属性值均以小写开头，
            d = eval(str(response.body.data))
            return d['Id'],key
        except Exception as error:
            # 如有需要，请打印 error
            UtilClient.assert_as_string(error.message)

    @staticmethod
    def QueryDocParserStatus(id):
        request = docmind_api20220711_models.QueryDocParserStatusRequest(
            # id :  任务提交接口返回的id
            id=id
        )
        try:
            # 复制代码运行请自行打印 API 的返回值
            response = aliDocAnalysis.client.query_doc_parser_status(request)
            # API返回值格式层级为 body -> data -> 具体属性。可根据业务需要打印相应的结果。获取属性值均以小写开头
            # 获取返回结果。建议先把response.body.data转成json，然后再从json里面取具体需要的值。
            d = eval(str(response.body.data))
            return d
        except Exception as error:
            # 如有需要，请打印 error
            UtilClient.assert_as_string(error.message)

    @staticmethod
    def GetDocParserResult(id,page=1,perPageNum=3000):
        request = docmind_api20220711_models.GetDocParserResultRequest(
            # id :  任务提交接口返回的id
            id=id,
            layout_step_size=perPageNum,
            layout_num=(page-1)
        )
        try:
            # 复制代码运行请自行打印 API 的返回值
            response = aliDocAnalysis.client.get_doc_parser_result(request)
            # API返回值格式层级为 body -> data -> 具体属性。可根据业务需要打印相应的结果。获取属性值均以小写开头
            # 获取返回结果。建议先把response.body.data转成json，然后再从json里面取具体需要的值。
            d = eval(str(response.body.data.get('layouts')))
            return d
        except Exception as error:
            # 如有需要，请打印 error
            UtilClient.assert_as_string(error.message)