# -*- coding: utf-8 -*-
# This file is auto-generated, don't edit it. Thanks.

from typing import List

from alibabacloud_dysmsapi20170525.client import Client as Dysmsapi20170525Client
from alibabacloud_credentials.client import Client as CredentialClient
from alibabacloud_tea_openapi import models as open_api_models
from alibabacloud_dysmsapi20170525 import models as dysmsapi_20170525_models
from alibabacloud_tea_util import models as util_models
from alibabacloud_credentials.models import Config
from conf.config import app_config

class aliSms:
    def __init__(self):
        pass

    @staticmethod
    def create_client() -> Dysmsapi20170525Client:
        """
        使用凭据初始化账号Client
        @return: Client
        @throws Exception
        """
        # 工程代码建议使用更安全的无AK方式，凭据配置方式请参见：https://help.aliyun.com/document_detail/378659.html。

        config1 = Config(
            type='access_key',
            access_key_id=app_config['ali_access_key'],
            access_key_secret=app_config['ali_access_key_secret'],
        )
        credential = CredentialClient(config1)
        config = open_api_models.Config(
            credential=credential
        )
        # Endpoint 请参考 https://api.aliyun.com/product/Dysmsapi
        config.endpoint = f'dysmsapi.aliyuncs.com'
        return Dysmsapi20170525Client(config)

    @staticmethod
    def sendRemind(mobile,name,template='0',remind_type="余额不足"):
        if remind_type =="余额不足":  #余额不足就是服务延续
            template_code = {'0':'SMS_489705352','1':'SMS_489880313','2':'SMS_491160010'}
        else:
            template_code = {'0':'SMS_489690320','1':'SMS_489710334','2':'SMS_490980015'}
        client = aliSms.create_client()
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest(
            sign_name='深圳市锋矢科技',
            template_code=template_code[template],
            phone_numbers=mobile,
            template_param='{"name":"'+name+'"}'
        )
        runtime = util_models.RuntimeOptions()
        try:
            rs = client.send_sms_with_options(send_sms_request, runtime)
            return rs
        except Exception as e:
            print(e)
            return 0

    @staticmethod
    def sendAdminRemind(name,serve_type,remind_type="余额不足"):
        from models.admin.model import AdminUser
        item = AdminUser.getOne(1)
        serve = {'0':"缺陷管理",'1':"需求管理",'2':"立项管理"}
        template_code = {'余额不足':'SMS_489755391','日期已到':'SMS_489770310'}
        client = aliSms.create_client()
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest(
            sign_name='深圳市锋矢科技',
            template_code=template_code[remind_type],
            phone_numbers=item.mobile,
            template_param='{"name":"'+name+'","serve_type":"'+serve[serve_type]+'"}'
        )
        runtime = util_models.RuntimeOptions()
        try:
            # 复制代码运行请自行打印 API 的返回值
            rs = client.send_sms_with_options(send_sms_request, runtime)
            return rs
        except Exception as e:
            print(e)
            return 0

    @staticmethod
    def sendAdminException(name) -> None:
        client = aliSms.create_client()
        templateCode = "SMS_486215198"
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest(
            sign_name='深圳市锋矢科技',
            template_code = templateCode,
            phone_numbers=app_config['dev_mobile'],
            template_param='{"name":"'+name+'"}'
        )
        runtime = util_models.RuntimeOptions()
        try:
            # 复制代码运行请自行打印 API 的返回值
            client.send_sms_with_options(send_sms_request, runtime)
        except Exception as e:
            print(e)


    @staticmethod
    def sendNum(mobile,code,template='reg') -> None:
        template_code = {'forget':'SMS_485395345','reg':'SMS_485365333','changeMobile':'SMS_489865210'}
        client = aliSms.create_client()
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest(
            sign_name='深圳市锋矢科技',
            template_code=template_code[template],
            phone_numbers=mobile,
            template_param='{"code":"'+code+'"}'
        )
        runtime = util_models.RuntimeOptions()
        try:
            # 复制代码运行请自行打印 API 的返回值
            client.send_sms_with_options(send_sms_request, runtime)
        except Exception as e:
            # 此处仅做打印展示，请谨慎对待异常处理，在工程项目中切勿直接忽略异常。
            # 错误 message
            print(e)
    @staticmethod
    async def sendAsync(
        args: List[str],
    ) -> None:
        client = aliSms.create_client()
        send_sms_request = dysmsapi_20170525_models.SendSmsRequest(
            sign_name='深圳市锋矢科技',
            template_code='SMS_106970112',
            phone_numbers='18320740477',
            template_param='{"code":"1234"}'
        )
        runtime = util_models.RuntimeOptions()
        try:
            # 复制代码运行请自行打印 API 的返回值
            await client.send_sms_with_options_async(send_sms_request, runtime)
        except Exception as e:
            print(e)