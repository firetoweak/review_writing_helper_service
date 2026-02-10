import time

import oss2
from conf.config import app_config
import os
import re
import base64
from  datetime import datetime
import requests
import shutil
from pathlib import PurePath

class aliOss():
    auth = oss2.Auth(app_config['ali_access_key'], app_config['ali_access_key_secret'])
    bucket = oss2.Bucket(auth, app_config['ali_endpoint'], app_config['ali_bucket'])
    @staticmethod
    def uploadFile(local_file=""):
        with open(local_file, mode="rb") as file:
            data = file.read()
        key = os.path.basename(local_file)
        aliOss.bucket.put_object(key, data)
        return key,aliOss.getUrl(key)

    @staticmethod
    def uploadSignDoc(local_file):
        with open(local_file, mode="rb") as file:
            data = file.read()
        headers = dict()
        headers["x-oss-storage-class"] = "Standard"
        headers["x-oss-object-acl"] = oss2.OBJECT_ACL_PRIVATE
        key ='docs/'+os.path.basename(local_file)
        aliOss.bucket.put_object(key, data, headers=headers)
        return key,aliOss.getUrl(key)


    @staticmethod
    def deleteFile(key):
        aliOss.bucket.delete_object(key)

    @staticmethod
    def getPicUrl(key):
        image_url = f"https://{app_config['ali_bucket']}.{app_config['ali_endpoint']}/{key}"
        return image_url

    @staticmethod
    def getUrl(key):
        url = aliOss.bucket.sign_url('GET', key, 600, slash_safe=True)
        return url
    @staticmethod
    def uploadPicData(key="",data=""):
        aliOss.bucket.put_object(key, data)
        return aliOss.getPicUrl(key)

    @staticmethod
    def extract_and_upload_base64_images(htmlContent,userId):
    # 正则表达式匹配Base64图片数据
        pattern = re.compile(r'src=["\']data:image/(.+?);base64,(.+?)["\']', re.DOTALL)
        matches = pattern.findall(htmlContent)
        # 用于存储新的HTML内容
        imageUrls = []
        erroeTag = 0
        for ext, base64_data in matches:
                # 去除可能的换行符和空格
                base64_data = base64_data.strip()
                # 解码Base64数据
                image_data = base64.b64decode(base64_data)
                # 生成OSS对象键（文件名）
                try:
                    object_key = datetime.now().strftime("%Y%m%d%H%M%S%f") + str(userId) +'.'+ ext
                    image_url = aliOss.uploadPicData(object_key,image_data)
                except Exception as e:
                    print(f"上传图片时出错: {e}")
                    image_url = ""
                    erroeTag = 1
                imageUrls.append(image_url)
                #单引号
                htmlContent = htmlContent.replace(
                    f'src="data:image/{ext};base64,{base64_data}"',
                    f'src="{image_url}"'
                )
                #双引号
                htmlContent = htmlContent.replace(
                    f"src='data:image/{ext};base64,{base64_data}'",
                    f'src="{image_url}"'
                )
        return htmlContent,erroeTag
    @staticmethod
    def extract_url_images(html_content, user_id):
        pattern = re.compile(r'<img[^>]*src=["\'](.*?)["\']', re.DOTALL)
        matches = pattern.findall(html_content)
        print(matches)
        new_html_content = html_content
        urls = []
        error_img = []
        error_tag = 0
        for src in matches:
            if src.startswith("https://jihebluearmy"):
                urls.append(src)
                continue
            if not src.startswith("http"):
                error_tag = 2
                if len(src)>200:
                    error_img.append(f'<img src="{src[0:200]}..." >')
                else:
                    error_img.append(f'<img src="{src[0:200]}" >')
                continue
            try:
                response = requests.get(src)
                response.raise_for_status()
                image_data = response.content
            except Exception as e:
                print("下载图片失败")
                error_tag = 2
                if len(src)>200:
                    error_img.append(f'<img src="{src[0:200]}..." >')
                else:
                    error_img.append(f'<img src="{src[0:200]}" >')
                continue
            ext = ''
            if image_data.startswith(b'\xff\xd8\xff'):
                ext = '.jpg'
            elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
                ext = '.png'
            elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
                ext =  '.gif'
            elif image_data.startswith(b'BM'):
                ext =  '.bmp'
            object_key = datetime.now().strftime("%Y%m%d%H%M%S%f") + str(user_id) + ext
            try:
                image_url = aliOss.uploadPicData(object_key,image_data)
            except Exception as e:
                print(f"上传图片时出错: {e}")
                error_tag = 1
                continue
            urls.append(image_url)
            new_html_content = new_html_content.replace(
                f'{src}',
                f'{image_url}'
            )
        return new_html_content,urls,error_tag,error_img
    @staticmethod
    def get_ai_contents(record_id,html_content,tag=0,ai_urls={}):
        if html_content is None:
            html_content = ""
        pattern = re.compile(r'<img\b[^>]*>', re.DOTALL)
        matches = pattern.findall(html_content)
        ai_content = html_content
        if matches:
            for m in matches:
                tag = tag+1
                img_tag = str(int(time.time() * 100000)) + str(record_id) + str(tag)
                ai_content = ai_content.replace(m,f"[IMAGE_{img_tag}]")
                pattern = re.compile(r'<img[^>]*src=["\'](.*?)["\']', re.DOTALL)
                url_matches = pattern.findall(m)
                if url_matches:
                    ai_urls[f"[IMAGE_{img_tag}]"] = url_matches[0]
        clean = re.compile('<.*?>')
        ai_content = re.sub(clean, '', ai_content)
        return ai_content,tag,ai_urls




    @staticmethod
    def dealImgSrc(html,userId):
        urls = []
        errorImg = []
        error = 0
        #html,error = aliOss.extract_and_upload_base64_images(html,userId)

        html,urls,error,errorImg = aliOss.extract_url_images(html,userId)
        return html,urls,error,errorImg
    @staticmethod
    def imgFileCheck(html_content,tmpIdPath):
        pattern = re.compile(r'<img[^>]*src=["\'](.*?)["\']', re.DOTALL)
        matches = pattern.findall(html_content)
        notExistsSrc = []
        for src in matches:
            if not os.path.exists(tmpIdPath+src):
                notExistsSrc.append(src)
        return notExistsSrc
    @staticmethod
    def extract_local_images(html_content, userId,tmpIdPath):
        pattern = re.compile(r'<img[^>]*src=["\'](.*?)["\']', re.DOTALL)
        matches = pattern.findall(html_content)
        urls = []
        for src in matches:
            try:
                local_file = f"./{tmpIdPath}/{src}"
                if os.path.exists(local_file):
                    with open(local_file, mode="rb") as file:
                        image_data = file.read()
                else:
                    print('图片不存在')
                    continue
                ext = ''
                if image_data.startswith(b'\xff\xd8\xff'):
                    ext = '.jpg'
                elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
                    ext = '.png'
                elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
                    ext = '.gif'
                elif image_data.startswith(b'BM'):
                    ext = '.bmp'
                # 生成OSS对象键（文件名）
                object_key = datetime.now().strftime("%Y%m%d%H%M%S%f") + str(userId)+ ext
                image_url = aliOss.uploadPicData(object_key,image_data)
                urls.append(image_url)
                html_content = re.sub(rf'(<img[^>]*src=["|\']){src}(["|\'][^>]*>)', rf'\g<1>{image_url}\g<2>',html_content)
            except Exception as e:
                print(f"上传图片时出错: {e}")
                return html_content,urls,0
        return html_content,urls,1
    @staticmethod
    def batch_download_images_from_oss(object_names, local_dir):
        try:
            pic_dicts ={}
            i = 0
            for object_name in object_names:
                i = i+1
                file_name =  f'{i}.'+os.path.basename(object_name).split('.')[-1]
                local_file_path = os.path.join(local_dir,file_name)
                try:
                    aliOss.bucket.get_object_to_file(os.path.basename(object_name),local_file_path)
                    pic_dicts[object_name] = [file_name,os.path.basename(object_name)]
                    # object_stream = aliOss.bucket.get_object(os.path.basename(object_name))
                    # with open(local_file_path, 'wb') as local_fileobj:
                    #     shutil.copyfileobj(object_stream, local_fileobj)
                    print(f"成功下载: {object_name} -> {local_file_path}")
                except oss2.exceptions.OssError as e:
                    print(f"下载 {object_name} 失败: {e}")
            return pic_dicts
        except oss2.exceptions.OssError as e:
            print(f"批量下载失败: {e}")
            return False

    @staticmethod
    def checkUrlOk(html_content):
        pattern = re.compile(r'<img[^>]*src=["\'](http.*?)["\']', re.DOTALL)
        matches = pattern.findall(html_content)
        new_html_content = html_content
        urls = []
        for src in matches:
            try:
                response = requests.get(src)
                response.raise_for_status()
                image_data = response.content
            except Exception as e:
                print("下载图片失败")
                urls.append(src)
        return urls

    @staticmethod
    def extract_export_data_images(html_content,picDict):
        if html_content==None:
            html_content=""
        pattern = re.compile(r'<img[^>]*src=["\'](.*?)["\']', re.DOTALL)
        matches = pattern.findall(html_content)
        for src in matches:
            print(src)
            try:
                l = picDict.get(src)
                if l!=None:
                    #html_content = html_content.replace(src,l[0])
                    html_content = re.sub(rf'<img[^>]*src=["|\']{src}["|\'][^>]*>', rf'\<img src="{l[0]}">',html_content)
            except Exception as e:
                print(f"图片替换出错: {e}")
        return html_content

    @staticmethod
    def downLoadOne(object_name,local_path):
        try:
            if not os.path.exists(local_path):
                os.mkdir(local_path)
            local_file_path = local_path +datetime.now().strftime("%Y%m%d%H%M%S%f")+"-"+os.path.basename(object_name)
            filename = datetime.now().strftime("%Y%m%d%H%M%S%f") +os.path.basename(object_name)
            aliOss.bucket.get_object_to_file(object_name, local_file_path)
            return local_file_path,filename
        except Exception as e:
            print(e)
            raise Exception('下载失败')