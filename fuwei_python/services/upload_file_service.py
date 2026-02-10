import os
import re
import time
from datetime import datetime

import requests
from flask import request, g, current_app, jsonify

from common.aliDocAnalysis import aliDocAnalysis
from common.aliOss import aliOss
from conf.config import app_config
from conf.db import db
from models.lx_ai_sug_score.model import LxAiSugScore
from models.project_document.model import DocumentAttachment
from utils.file_handler import FileHandler


class UploadFileService:
    @staticmethod
    def upload_files(file,user_id=""):
        name_ext = file.filename
        extension = os.path.splitext(name_ext)[-1]
        file_name = os.path.splitext(name_ext)[0]
        tmp_id_path = f'./tmp/upload/{g.user_id}/'
        if not os.path.exists(tmp_id_path):
            os.mkdir(tmp_id_path)
        tmp_file_name =file_name+ datetime.now().strftime("%Y%m%d%H%M%S%f")+str(g.user_id)+extension
        file.save(f'{tmp_id_path}{tmp_file_name}')
        key,url = aliOss.uploadFile(f'./tmp/upload/{user_id}/{tmp_file_name}')
        file_info = FileHandler.get_file_info(f'{tmp_id_path}{tmp_file_name}')
        os.remove(f'{tmp_id_path}{tmp_file_name}')
        return key,url,file_info
    @staticmethod
    def ai_deal(user_id, ali_key, cache, record_id):
        from app import app
        with app.app_context():
            try:
                download_tmp_path = f"./tmp/download/{user_id}/"
                tmp_id_path_file,_ = aliOss.downLoadOne(ali_key, download_tmp_path)
                ali_id, key = aliDocAnalysis.SubmitDocParserJob(tmp_id_path_file)
            except:
                cache.update({str(user_id) + "upload_state" + str(record_id): "upload_failed"})
                return "" , {}
            cache.update({str(user_id) + "upload_state" + str(record_id): "aliOss_finish"})
            mark_down_text = ""
            image_url = {}
            page = 1
            per_page_num = 3000
            last_number_of_successful_parsing = -1
            pattern = r'!\[(.*?)\]\((http://docmind-api-cn-hangzhou.oss-cn-hangzhou.aliyuncs.com.+?)\)'
            tag = 0
            try:
                while (True):
                    d = aliDocAnalysis.QueryDocParserStatus(ali_id)
                    if d['Status'] == 'Fail':
                        cache.update({str(user_id) + "upload_state" + str(record_id): "upload_failed"})
                        break
                    if last_number_of_successful_parsing < d['NumberOfSuccessfulParsing']:
                        last_number_of_successful_parsing = d['NumberOfSuccessfulParsing']
                    else:
                        if last_number_of_successful_parsing == 0 and d['Status'] == "success":
                            break
                        time.sleep(1)
                        continue
                    datas = aliDocAnalysis.GetDocParserResult(ali_id, page, per_page_num)
                    if last_number_of_successful_parsing <= page * per_page_num and d['Status'] == 'success':
                        for data in datas:
                            match = re.match(pattern, data['markdownContent'])
                            if match:
                                img_tag = str(int(time.time() * 100000))+str(user_id)+str(tag)
                                object_key = UploadFileService.download_upload(match.group(2))
                                image_url[f'[IMAGE_{img_tag}]'] = object_key
                                data['markdownContent'] = f'[IMAGE_{img_tag}]'
                                tag = tag+1
                            mark_down_text = mark_down_text + data['markdownContent']
                        break
                    elif last_number_of_successful_parsing <= page * per_page_num and d['Status'] == 'Processing':
                        time.sleep(1)
                        continue
                    elif last_number_of_successful_parsing > page * per_page_num and (
                            d['Status'] == 'Processing' or d['Status'] == 'success'):
                        for data in datas:
                            match = re.match(pattern, data['markdownContent'])
                            if match:
                                img_tag = str(int(time.time() * 100000))+str(user_id)+str(tag)
                                object_key = UploadFileService.download_upload(match.group(2))
                                image_url[f'[IMAGE_{img_tag}]'] = object_key
                                data['markdownContent'] = f'[IMAGE_{img_tag}]'
                                tag = tag+1
                            mark_down_text = mark_down_text + data['markdownContent']
                        page = page + 1
                if mark_down_text == "":
                    cache.update({str(user_id) + "upload_state" + str(record_id): "empty_file"})
                else:
                    cache.update({str(user_id) + "upload_state" + str(record_id): "all_finish"})
                os.remove(f'{tmp_id_path_file}')
                return mark_down_text,image_url
            except Exception as e:
                print('upload_failed')
                print(str(e))
                cache.update({str(user_id) + "upload_state" + str(record_id): "upload_failed"})
                return "" , {}

    @staticmethod
    def lx_deal_markdown(user_id, key, cache, record_id):
        mark_down_text,_ =UploadFileService.ai_deal(user_id, key, cache, record_id)
        if mark_down_text == "":
            LxAiSugScore.delEmpty(record_id, user_id)
        else:
            LxAiSugScore.saveMarkdown(record_id, mark_down_text, key)
    @staticmethod
    def project_document_deal_att_markdown(attachment,project_doc_id,cache,user_id=0):

        from app import app
        with app.app_context():
            # 保存附件记录
            doc_attachment = DocumentAttachment(
                document_id=project_doc_id,
                filename=attachment.get('name'),
                file_url=attachment.get('key'),  # 假设前端已上传文件并返回URL
                mime_type=attachment.get('mimeType'),
                file_size=attachment.get('size'),
                is_in_knowledge_base=False,
                created_at=datetime.now()
            )
            db.session.add(doc_attachment)
            db.session.flush()
            record_id = doc_attachment.id
            cache.setdefault(str(user_id) + "upload_state" + str(record_id), "uploading")
            mark_down_text,image_urls = UploadFileService.ai_deal(user_id, attachment.get('key'), cache, record_id)
            DocumentAttachment.query.filter_by(id=record_id).update({"content":mark_down_text,"img_urls":image_urls})
            db.session.commit()

    @staticmethod
    def get_upload_state():
        cache = current_app.extensions.get('cache')
        record_id = request.values.get('id', 0)
        state = cache.get(str(g.user_id) + "upload_state" + str(record_id))
        if state == 'aliOss_finish':
            return jsonify({'msg': '阿里云oss上传成功', "percent": 75, 'code': 1}), 200
        elif state == 'all_finish':
            return jsonify({'msg': '阿里云解析完成', "percent": 100, 'code': 1}), 200
        elif state == 'uploading':
            return jsonify({'msg': '上传服务器本地', "percent": 50, 'code': 1}), 200
        elif state == 'empty_file':
            return jsonify({'msg': '文件内容为空，请检查上传文件，重新上传', "percent": -1, 'code': 1}), 200
        else:
            return jsonify({'msg': '服务器错误', "percent": -1, 'code': 1}), 200

    @staticmethod
    def download_upload(src, user_id=1):
        try:
            response = requests.get(src)
            response.raise_for_status()
            image_data = response.content
        except Exception as e:
            print("下载图片失败")
            error_tag = 2
        ext = ''
        if image_data.startswith(b'\xff\xd8\xff'):
            ext = '.jpg'
        elif image_data.startswith(b'\x89PNG\r\n\x1a\n'):
            ext = '.png'
        elif image_data.startswith(b'GIF87a') or image_data.startswith(b'GIF89a'):
            ext = '.gif'
        elif image_data.startswith(b'BM'):
            ext = '.bmp'
        object_key = datetime.now().strftime("%Y%m%d%H%M%S%f") + str(user_id) + ext
        aliOss.uploadPicData(object_key, image_data)
        return f"https://{app_config['ali_bucket']}.{app_config['ali_endpoint']}/{object_key}"

