const { createEditor, createToolbar } = window.wangEditor
const editorConfig = {
    placeholder: '请输入...',
    MENU_CONF: {
        uploadImage: {
            server: '/user/aiVal/upload_pic', // 替换为你的图片上传接口地址
            fieldName: 'file', // 上传文件的字段名（与后端一致）
            maxFileSize: 5 * 1024 * 1024, // 5MB
            maxNumberOfFiles: 1, // 最多上传 5 张图片
            customInsert(res, insertFn) {
                if (res.code == 1) {
                    insertFn(res.url); // 插入图片 URL
                } else {
                    alert(res.msg || '上传失败');
                }
            }
        }
    }
}
const toolbarConfig = {
    toolbarKeys: ['uploadImage'] // 只保留上传图片按钮
};
const editor1 = createEditor({
    selector: '#e1',
    html: '',
    config: { ...editorConfig },
    mode: 'simple', // or 'simple'
})
createToolbar({
    editor:editor1,
    selector: '#tb1',
    config: toolbarConfig,
    mode: 'simple', // or 'simple'
})