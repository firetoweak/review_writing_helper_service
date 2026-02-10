import oss2
from conf.config import app_config

# endpoint = 'http://oss-cn-beijing.aliyuncs.com' # Suppose that your bucket is in the Hangzhou region.
# auth = oss2.Auth(app_config['ali_access_key'], app_config['ali_access_key_secret'])
# bucket = oss2.Bucket(auth, app_config['ali_endpoint'], app_config['ali_bucket'])
#
# # The object key in the bucket is story.txt
# key = '333.png'
# with open(key, mode="rb") as file:
#     data = file.read()
# # Upload
# rs = bucket.put_object(key, data)
# print(rs)
# # # Download
# # bucket.get_object(key).read()
# #
# # # Delete
# # bucket.delete_object(key)
#
# # Traverse all objects in the bucket
# for object_info in oss2.ObjectIterator(bucket):
#     print(object_info.key)