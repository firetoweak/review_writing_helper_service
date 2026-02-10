import zipfile
import os
import chardet

class zip():
    @staticmethod
    def extractWithEncoding(zip_path, extract_to):  #gbk
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for file_info in zf.infolist():
                try:
                    # 尝试用指定编码解码文件名  默认gbk，即windows
                    detected_encoding = chardet.detect(file_info.filename.encode('cp437'))['encoding']
                except:
                    raise Exception('文件编码错误！！')
                try:
                    filename = file_info.filename.encode('cp437').decode(detected_encoding)
                except:
                    raise Exception('文件编码错误！！')
                if filename.endswith('/'):
                    os.makedirs(extract_to+filename, exist_ok=True)
                    continue
                try:
                    with zf.open(file_info) as src, open(f"{extract_to}/{filename}", 'wb') as dst:
                        dst.write(src.read())
                except Exception as e:
                    print(e)
                    continue

    @staticmethod
    def zipDirectory(directory_path, zip_path):
        """
        将指定目录中的所有文件打包成 ZIP 文件

        参数:
            directory_path: 要打包的目录路径
            zip_path: 生成的 ZIP 文件路径
        """
        # 确保目录路径存在
        if not os.path.exists(directory_path):
            raise FileNotFoundError(f"目录不存在: {directory_path}")

        # 创建 ZIP 文件
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            # 遍历目录中的所有文件和子目录
            for root, dirs, files in os.walk(directory_path):
                for file in files:
                    # 获取文件的完整路径
                    file_path = os.path.join(root, file)
                    # 在 ZIP 文件中创建相对路径
                    arcname = os.path.relpath(file_path, start=directory_path)
                    # 将文件添加到 ZIP 中
                    zipf.write(file_path, arcname)

        print(f"成功创建 ZIP 文件: {zip_path}")
