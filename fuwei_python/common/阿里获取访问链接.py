import oss2
from conf.config import app_config
from oss2.credentials import EnvironmentVariableCredentialsProvider
endpoint = 'http://oss-cn-beijing.aliyuncs.com' # Suppose that your bucket is in the Hangzhou region.
auth = oss2.Auth(app_config['ali_access_key'], app_config['ali_access_key_secret'])
region = "cn-beijing"
bucket = oss2.Bucket(auth, endpoint, 'test19850711',region=region)
object_name = '返回测试.docx'
url = bucket.sign_url('GET', object_name, 60, slash_safe=True)
print(url)