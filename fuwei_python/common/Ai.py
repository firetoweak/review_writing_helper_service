from flask import current_app
from openai import OpenAI
from models.model.model import Models
import json
from models.doc_files.model import DocFiles
from models.ai_sug_score.model import AiSugScore
from models.lx_ai_sug_score.model import LxAiSugScore
import requests
from conf.config import app_config
from models.users.models import User
from user.routes import getToken

class Ai():
    @staticmethod
    def get_answer_by_content(question="", content="", before_content=""):
        usingModel = Models.getUsingModel()
        client = OpenAI(api_key=usingModel['api_key'], base_url= usingModel['base_url'])
        aiContent = f'''
        问题：{question}
        ####
        内容：\n
        {content}
        ###
        前几轮的问答:\n
        {before_content}
        '''
        response = client.chat.completions.create(
            model= usingModel['model_name'],
            messages = [
                {"role": "system", "content": "请根据给出的内容与之前几轮的问答回答问题，答案只能内容与前几轮的问答中查找！"},
                {"role": "user", "content": aiContent},
            ],
            stream=False
        )
        return response.choices[0].message.content

    @staticmethod
    def get_score_suggestion(record_type, data, model=None):
        print(f"model_name:{model['model_name']}")
        client = OpenAI(api_key=model['api_key'], base_url= model['base_url'])
        standard_file = DocFiles.getStandarFile(str(record_type))
        file_name = standard_file.file_name
        content = standard_file.markdown
        command = standard_file.cammand
        print("大模型请求中。。")
        sys_content = f"""
        {command}
        #####
        {file_name}的内容：
        {content}
        """
        if record_type==1:
            user_content = f"""
                需求描述:
                {data['step1']}
                ######
                需求分析:
                {data['step2']}
                #####
                需求决策:
                {data['step3']}
                ######
                验证结果:
                {data['step4']}
            """
        else:
            user_content = f"""
                产品缺陷描述:
                {data['step1']}
                ######
                原因分析:
                {data['step2']}
                #####
                解决措施实施:
                {data['step3']}
                ######
                回归测试:
                {data['step4']}
            """
        response = None
        try:
            response = client.chat.completions.create(
                model= model['model_name'],
                messages = [
                    {"role": "system","content": sys_content},
                    {"role": "user", "content": user_content},
                ],
                timeout=600,
                stream=False,
                temperature=0.2,
                top_p=0.4,
            )
        except Exception as e:
            current_app.logger.info_module(
                f"评估失败异常-get_score_suggestion-{model['model_name']}：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",
                module="model"
            )
            if response is not None and response.content:
                current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}","model")
            data['state'] = -3
            data['error_message'] = "请求超时"
            return data
        try:
            content = response.choices[0].message.content
            matches =  Ai.extract_balanced_braces(content)
            dic_result = json.loads(matches[0])
            for v in  AiSugScore.columnStep:
                data['ai_'+v] = f"""<b>评估依据：</b>
                {dic_result[v]["evaluate"]}<br>
                <b>改进建议：</b>
                {dic_result[v]["suggestion"]}
                """
                data[v+'_score'] = dic_result[v]["score"]
            data['state'] = 1
        except Exception as e:
            current_app.logger.info_module(f"评估失败异常-get_score_suggestion:{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",'model')
            if response is not None and response.content:
                current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}","model")
            data['state'] = -4
            data['error_message'] = "返回数据错误：" + str(response)
        data['model_name'] = model['name']
        return data

    @staticmethod
    def get_xjqw_score_suggestion(data, model=None, record_type=0):
        data['model_name'] = model['name']
        try:
            url = model['base_url']
            payload = AiSugScore.get_pay_load(data, record_type)
            print("ai_payload:")
            print(payload)
            headers = {
                "Content-Type": "application/json",
                "Authorization": "Bearer token123"
            }
            response = None
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=600
            )
            dic_result = response.json()
        except Exception as e:
            current_app.logger.info_module(f"评估失败异常-get_xjqw_score_suggestion-1：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}","model")
            if response is not None and response.content:
                current_app.logger.info_module(f"respones:{response.content.decode('utf-8')}","model")
            data['state'] = -3
            data['error_message'] =  f"请求接口失败"
            return data
        try:
            if dic_result['erro_code']== 0:
                result = dic_result['result']
                data.update(dic_result)
                for step in AiSugScore.columnStep:
                    data['ai_'+step] = f"""<b>评估依据：</b>
                    {result[step]["evaluate"]}<br>
                    <b>改进建议：</b>
                    {result[step]["suggestion"]}
                    """
                    data[step+'_score'] = result[step]["score"]
                data['state'] = 1
            else:
                data['state'] = -4
                data['error_message'] = f"AI接口返回错误,返回数据：{json.dumps(dic_result)}"
                current_app.logger.info_module(f"评估失败异常-get_xjqw_score_suggestion-2：返回数据：{json.dumps(dic_result)}","model")
        except Exception as e:
            current_app.logger.info_module(f"评估失败异常-get_xjqw_score_suggestion-3：{e},返回数据：{json.dumps(dic_result)}","model")
            data['state'] = -4
            data['error_message'] =  f"文件：ai.py;{e},行数：{e.__traceback__.tb_lineno},返回数据：{json.dumps(dic_result)}"
        return data

    @staticmethod
    def get_lx_content_score_suggestion(record_type, data,model, t=0, error_mess="")->{}:
        client = OpenAI(api_key=model['api_key'], base_url= model['base_url'])
        standard_file = DocFiles.getStandarFile(record_type, data['child_type_1'], data['child_type_2'], data['stepNum'])#总结
        content0 = standard_file.markdown_content #内容
        content1 = standard_file.markdown #评估
        command = standard_file.cammand
        print("大模型请求中getLxContentScoreSuggestion。。")
        user_content = f"""
        {command}
        ###
        附件1内容：
        {data['markdown']}
        ###
        附件2的内容：
        {content0}
        ###
        附件3的内容：
        {content1}
        ###
        特别注意，不要在回复中提及回复内容是附件2、附件3里的内容
        """
        state =1
        ai_return = {}
        response = None
        try:
            response = client.chat.completions.create(
                model= model['model_name'],
                messages = [
                    {"role": "user", "content": user_content},
                ],
                timeout=600,
                stream=False,
                temperature=0.2,
                top_p=0.4,
            )
            content = response.choices[0].message.content
            matches =  Ai.extract_balanced_braces(content)
            dic_result = json.loads(matches[0])
            ai_return['step_'+str(data['stepNum'])] = dic_result['content']
            ai_return['step_'+str(data['stepNum'])+'_score'] = dic_result['score']
            ai_return['step_'+str(data['stepNum'])+'_ai'] = f"""
            <b>{LxAiSugScore.PART_TXT[int(data['stepNum'])][0]}</b>
            {dic_result["evaluate"]}<br>
            <b>{LxAiSugScore.PART_TXT[int(data['stepNum'])][1]}</b>
            {dic_result["suggestion"]}
            """
            ai_return['error_mess'] = ""
        except Exception as e :
            current_app.logger.info_module(f"立项评估失败异常：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}","model")
            if response is not None and response.content:
                current_app.logger.info_module(f"response：{response.content.decode('utf-8')}","model")
            current_app.logger.info_module(f"ai_return：{ai_return}", "model")
            ai_return['step_'+str(data['stepNum'])] = ''
            ai_return['step_'+str(data['stepNum'])+'_score'] = -1
            ai_return['step_'+str(data['stepNum'])+'_ai'] = ""
            state = -3
            ai_return['error_mess'] = error_mess+f'{e}'
            if t <=2:
                t = t+1
                return Ai.get_lx_content_score_suggestion(record_type, data,model, t, ai_return['error_mess'])
        return ai_return,state

    @staticmethod
    def get_summarize(ArticelContent, t=0):
        usingModel = Models.getUsingModel()
        client = OpenAI(api_key=usingModel['api_key'], base_url= usingModel['base_url'])
        StandarFile = DocFiles.getStandarFile("2", 100, 1)
        cammand = StandarFile.cammand
        print("大模型请求中getSummarize。。")
        user_content = f"""
        {cammand}
        ####
        立项文档：
        {ArticelContent}
        """
        aiReturn = {}
        state = 1
        response = None
        try:
            response = client.chat.completions.create(
                model= usingModel['model_name'],
                messages = [
                    {"role": "user", "content": user_content},
                ],
                timeout=600,
                stream=False,
                temperature=0.2,
                top_p=0.4,
            )
            aiReturn['summarize_text'] =   response.choices[0].message.content
            aiReturn['error_mess'] = ""
        except Exception as e:
            current_app.logger.info_module(f"立项评估get_summarize异常：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}","model")
            if response is not None and response.content:
                current_app.logger.info_module(f"response：{response.content.decode('utf-8')}","model")
            current_app.logger.info_module(f"aiReturn：{aiReturn}", "model")
            aiReturn['summarize_text'] = ""
            state = -3
            aiReturn['error_mess'] = "getSummarize:请求超时"
            if t<=2:
                t=t+1
                return Ai.get_summarize(ArticelContent, t)
        return aiReturn,state

    @staticmethod
    def get_xmind(ArticelContent, error_mess='', t=0):
        usingModel = Models.getQwPlus()
        client = OpenAI(api_key=usingModel['api_key'], base_url= usingModel['base_url'])
        StandarFile = DocFiles.getStandarFile("2", 100, 2)
        cammand = StandarFile.cammand
        print(f"大模型请求中xmind{t}。。")
        system_content = f"""
            {cammand}
        """
        user_content = f"""
        立项文档内容：
        {ArticelContent}
        """
        aiReturn = {}
        state = 1
        response = None
        try:
            response = client.chat.completions.create(
                model= usingModel['model_name'],
                messages = [
                    {"role": "system", "content": system_content},
                    {"role": "user", "content": user_content},
                ],
                response_format={"type": "json_object"}
            )
            content = response.choices[0].message.content
            #matches =  Ai.extract_balanced_braces(content)
            aiReturn['xmind_json'] = content
            aiReturn['error_mess'] = ""
            xmindJson = json.loads(aiReturn['xmind_json'])
        except Exception as e:
            aiReturn['xmind_json'] = ''
            aiReturn['error_mess'] =error_mess+f'getXmind:{e}'
            current_app.logger.info_module(f"立项评估get_xmind异常：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}","model")
            if response is not None and response.content:
                current_app.logger.info_module(f"response：{response.content.decode('utf-8')}","model")
            current_app.logger.info_module(f"aiReturn：{aiReturn}","model")
            state = -3
            if t<=2:
                t=t+1
                return Ai.get_xmind(ArticelContent, aiReturn['error_mess'], t)
        return aiReturn,state

    @staticmethod
    def summarize_val_sug(item, t=0):
        '''

        :param item:
        :param t:
        :return:
        '''
        aiReturn = {}
        for i in range(1,6):
            txt = str(getattr(item,f'step_{i}_ai'))
            if txt =='' or txt==None:
                aiReturn['summarize_val_sug'] = None
                aiReturn['error_mess'] = f''
                state = -3
                return aiReturn,state
        child_type_2 = 1
        if item.case == 1 or item.case ==2:
            child_type_2 = item.case
        else:
            child_type_2 = 3
        cammand = DocFiles.getSumarizeDesCase(child_type_2)
        print("大模型请求中summarize_val_sug")
        user_content = ""
        if child_type_2 == 1:
            user_content = item.step_1_ai+item.step_2_ai+cammand
        elif child_type_2 == 2:
            user_content = item.step_1_ai+item.step_2_ai+item.step_3_ai+cammand
        elif child_type_2 == 3:
            user_content = item.step_1_ai+item.step_2_ai+item.step_3_ai+item.step_4_ai+item.step_5_ai+cammand
        user_content = f"""###
                        【工作质量评估意见和改进建议】
                        {user_content}
                        """
        usingModel = Models.getUsingModel()
        client = OpenAI(api_key=usingModel['api_key'], base_url= usingModel['base_url'])
        state = 1
        response = None
        aiReturn = {}
        try:
            response = client.chat.completions.create(
                model= usingModel['model_name'],
                messages = [
                    {"role": "user", "content": user_content},
                ],
                stream=False,
                temperature=0.2,
                top_p=0.4,
            )
            aiReturn['summarize_val_sug'] = response.choices[0].message.content
            aiReturn['error_mess'] = ""
        except Exception as e:
            current_app.logger.info_module(f"立项评估summarize_val_sug异常：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",'model')
            if response is not None and response.content:
                current_app.logger.info_module(f"response：{response.content.decode('utf-8')}","model")
            current_app.logger.info_module(f"aiReturn：{aiReturn}","model")
            aiReturn['summarize_val_sug'] = None
            aiReturn['error_mess'] =f'summarizeValSug:{e}'
            state = -3
            if t<=2:
                t=t+1
                return Ai.summarize_val_sug(item, t)
            else:
                return aiReturn,state
        return aiReturn,state
    @staticmethod
    def askScoreSuggestionTable(markdown_table,question,type):
        if type == "0":
            role = "产品缺陷管理专家"
        else:
            role = "需求管理专家"
        StandarFile = DocFiles.getStandarFile(str(type))
        fileName = StandarFile['name']
        content = StandarFile['content']
        sys_content = f'''
        以下html表格是你之前作为{role}以{fileName}作为标准对文档的的工作质量进行打分以及建议,文档作者对你的评分以及建议作出了提问，请你继续以{role}的身份以{fileName}作为依据回答文档作者的提问,所有的回复只能和
        {fileName}有关，不得提及任何无关的内容
        #####
        {fileName}的内容：
        {content}
        '''
        user_content = f'''
        评分建议表格：
        {markdown_table}
        这里是文档作者对评分以及建议的提问：
        {question}
        '''
        usingModel = Models.getUsingModel()
        client = OpenAI(api_key=usingModel['api_key'], base_url= usingModel['base_url'])
        response = client.chat.completions.create(
            model= usingModel['model_name'],
            messages = [
                {"role": "system", "content":sys_content},
                {"role": "user", "content": user_content},
            ],
            stream=False,
            temperature=0.2,
            top_p=0.4,
        )
        return response.choices[0].message.content
    @staticmethod
    def extract_balanced_braces(s):
        stack = []
        result = []
        current = []
        for i, char in enumerate(s):
            current.append(char)
            if char == '{':
                stack.append(i)
            elif char == '}':
                if stack:
                    start = stack.pop()
                    if not stack:  # 找到一个完整的嵌套结构
                        # 提取从 start 到当前索引的子字符串（不包括外层的括号，如果需要可以调整）
                        balanced_str = ''.join(current[start:i+1])
                        # 递归处理嵌套（如果需要提取所有嵌套级别，可以在这里递归调用）
                        # 这里只是简单示例，不递归提取内部嵌套
                        result.append(balanced_str)
                        # 清除当前缓冲区中已处理的部分（根据需要调整）
                        current = current[:start]  # 或者使用其他逻辑来继续解析
        # 注意：这个示例没有递归处理嵌套的大括号，只是展示了如何找到顶层的大括号对
        # 如果需要递归提取所有级别的嵌套，需要更复杂的逻辑
        return result
    @staticmethod
    def val_score_twice(content, step):
        content = content.split(LxAiSugScore.PART_TXT[int(step)][1])[0]
        command = DocFiles.getTwiceScoreCammand(step)
        print("valScoreTwice大模型请求中")
        user_content = f"""
        {content}
        ###
        {command}
        """
        using_model = Models.getUsingModel()
        client = OpenAI(api_key=using_model['api_key'], base_url= using_model['base_url'])
        try:
            response = client.chat.completions.create(
                model= using_model['model_name'],
                messages = [
                    {"role": "user", "content": user_content},
                ],
                stream=False,
                temperature=0.2,
                top_p=0.4,
            )
            return response.choices[0].message.content
        except Exception as e:
            current_app.logger.error(f"评估失败异常-val_score_twice：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数;{e.__traceback__.tb_lineno}")
            raise Exception("评估失败")

    @staticmethod
    def my_val_api_done(payload,user_id):
        item = User.get_user_by_id(user_id)
        if item.token=="" or item.token is None:
            getToken()
            item = User.get_user_by_id(user_id)
        token = item.token
        payload['token'] = token
        response = None
        try:
            protocol = 'http://' if app_config['env'] == "dev" or app_config['env'] == "local" else "https://"
            url = f"{protocol}{app_config['domain']}/user/api/ai_val"
            headers = {
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Content-Type": "application/json"
            }
            response = requests.request("POST", url, data=json.dumps(payload), headers=headers,timeout=600)
            return response.text
        except Exception as e:
            current_app.logger.info_module(f"调用评估接口my_val_api_done异常：{e},文件：{e.__traceback__.tb_frame.f_globals['__file__']};行数：{e.__traceback__.tb_lineno}",'model')
            if response is not None and response.content:
                current_app.logger.info_module(f"response：{response.content.decode('utf-8')}","model")
            raise Exception("评估失败")