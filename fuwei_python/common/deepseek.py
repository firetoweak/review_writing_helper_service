from openai import OpenAI

client = OpenAI(api_key="sk-23c878b5d8bc4396a3797e1625356897", base_url="https://api.deepseek.com")
#sk-23c878b5d8bc4396a3797e1625356897
# response = client.chat.completions.create(
#     #deepseek-chat
#     model="deepseek-chat",
#     messages=[
#         {"role": "system", "content": "You are a helpful assistant"},
#         {"role": "user", "content": "詹姆斯和乔丹谁更牛b"},
#     ],
#     stream=False
# )
sys_content = """



"""
user_content = """
<img src="http://jihebluearmy.oss-cn-shenzhen.aliyuncs.com/2025051310082896367776.png" alt="" data-href="" style="">
请问img标签里的图片显示的是什么内容？
"""
completion = client.chat.completions.create(
    model="deepseek-reasoner",  # 此处以 deepseek-r1 为例，可按需更换模型名称。
    messages=[
        #{'role': 'system', 'content': sys_content},
        {'role': 'user', 'content': user_content}
    ],
    stream=False
)

# # 通过reasoning_content字段打印思考过程
# print("思考过程：")
# print(completion.choices[0].message.reasoning_content)

# 通过content字段打印最终答案
print(completion.choices[0].message.content)