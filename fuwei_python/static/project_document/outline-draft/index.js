// static/project_document/outline-draft/index.js
document.addEventListener('DOMContentLoaded', () => {
  const go = (path) => () => window.location.href = path;

  // Toast提示函数
  const flash = (text, type = 'info') => {
    const hint = document.createElement('div');
    hint.className = `toast-hint toast-${type}`;
    hint.innerText = text;
    document.body.appendChild(hint);
    setTimeout(() => {
      hint.classList.add('show');
    }, 10);
    setTimeout(() => {
      hint.classList.remove('show');
      setTimeout(() => hint.remove(), 200);
    }, 3000);
  };

  // 显示/隐藏错误消息
  const showError = (elementId, message) => {
    const errorEl = document.getElementById(elementId);
    if (errorEl) {
      errorEl.textContent = message;
      errorEl.style.display = 'block';
    }
  };

  const hideError = (elementId) => {
    const errorEl = document.getElementById(elementId);
    if (errorEl) {
      errorEl.style.display = 'none';
    }
  };

  // 计时相关变量
  let generateTimerInterval = null;
  let generateSeconds = 0;
  let isGenerating = false;

  // 开始计时器
  const startGenerateTimer = () => {
    stopGenerateTimer();
    generateSeconds = 0;

    const timeElement = document.getElementById('generate-outline-time');
    if (timeElement) {
      timeElement.textContent = '00:00';
    }

    generateTimerInterval = setInterval(() => {
      generateSeconds++;
      const minutes = Math.floor(generateSeconds / 60);
      const seconds = generateSeconds % 60;
      const formattedTime =
        minutes.toString().padStart(2, '0') + ':' +
        seconds.toString().padStart(2, '0');

      const timeElement = document.getElementById('generate-outline-time');
      if (timeElement) {
        timeElement.textContent = formattedTime;
      }
    }, 1000);
  };

  // 停止计时器
  const stopGenerateTimer = () => {
    if (generateTimerInterval) {
      clearInterval(generateTimerInterval);
      generateTimerInterval = null;
    }
  };

  // 显示生成大纲弹窗
  const showGenerateOutlineModal = () => {
    const modal = document.getElementById('generate-outline-overlay');
    if (modal) {
      modal.classList.add('show');
    }

    // 重置计时器
    const timeElement = document.getElementById('generate-outline-time');
    if (timeElement) {
      timeElement.textContent = '00:00';
    }

    // 开始计时
    startGenerateTimer();
    isGenerating = true;
  };

  // 隐藏生成大纲弹窗
  const hideGenerateOutlineModal = () => {
    const modal = document.getElementById('generate-outline-overlay');
    if (modal) {
      modal.classList.remove('show');
    }

    // 停止计时
    stopGenerateTimer();
    isGenerating = false;
  };

  // 显示生成成功弹窗
  const showGenerateSuccessModal = () => {
    const modal = document.getElementById('generate-success-overlay');
    if (modal) {
      modal.classList.add('show');
    }
  };

  // 隐藏生成成功弹窗
  const hideGenerateSuccessModal = () => {
    const modal = document.getElementById('generate-success-overlay');
    if (modal) {
      modal.classList.remove('show');
    }
  };

  // 显示生成失败弹窗
  const showGenerateErrorModal = (message) => {
    const modal = document.getElementById('generate-error-overlay');
    const messageElement = document.getElementById('generate-error-message');

    if (modal && messageElement) {
      messageElement.textContent = message || '未知错误';
      modal.classList.add('show');
    }
  };

  // 隐藏生成失败弹窗
  const hideGenerateErrorModal = () => {
    const modal = document.getElementById('generate-error-overlay');
    if (modal) {
      modal.classList.remove('show');
    }
  };

  // 存储已上传文件信息
  let uploadedFiles = [];

  // 当前要删除的文件信息
  let currentFileToDelete = null;
  let currentCardToDelete = null;

  // 获取已上传的文件信息
  const getUploadedFiles = () => {
    return uploadedFiles.map(file => ({
      name: file.name,
      url: file.url,
      mimeType: file.mimeType,
      size: file.size,
      key: file.file_path
    }));
  };

  // 获取CSRF token（如果有）
  const getCSRFToken = () => {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  };

  // 显示删除确认对话框
  const showDeleteConfirm = (fileInfo, cardElement) => {
    currentFileToDelete = fileInfo;
    currentCardToDelete = cardElement;

    const deleteOverlay = document.getElementById('delete-confirm-overlay');
    const deleteTitle = document.getElementById('delete-confirm-title');
    const fileName = fileInfo.original_name || fileInfo.name;

    if (deleteTitle) {
      deleteTitle.textContent = `确定删除文件"${fileName}"吗？`;
    }

    if (deleteOverlay) {
      deleteOverlay.classList.add('show');
    }
  };

  // 隐藏删除确认对话框
  const hideDeleteConfirm = () => {
    const deleteOverlay = document.getElementById('delete-confirm-overlay');
    if (deleteOverlay) {
      deleteOverlay.classList.remove('show');
    }
    currentFileToDelete = null;
    currentCardToDelete = null;
  };

  // 初始化删除确认对话框事件
  const initDeleteConfirmDialog = () => {
    const deleteOverlay = document.getElementById('delete-confirm-overlay');
    const cancelBtn = document.getElementById('delete-confirm-cancel');
    const confirmBtn = document.getElementById('delete-confirm-confirm');

    // 点击遮罩层关闭
    if (deleteOverlay) {
      deleteOverlay.addEventListener('click', (e) => {
        if (e.target === deleteOverlay) {
          hideDeleteConfirm();
        }
      });
    }

    // 取消按钮
    if (cancelBtn) {
      cancelBtn.addEventListener('click', hideDeleteConfirm);
    }

    // 确认删除按钮
    if (confirmBtn) {
      confirmBtn.addEventListener('click', async () => {
        if (currentFileToDelete && currentCardToDelete) {
          await deleteFile(currentFileToDelete, currentCardToDelete);
          hideDeleteConfirm();
        }
      });
    }
  };

  // 初始化生成大纲弹窗事件
  const initGenerateOutlineDialog = () => {
    const cancelBtn = document.getElementById('generate-outline-cancel');
    const successBtn = document.getElementById('generate-success-confirm');
    const errorBtn = document.getElementById('generate-error-close');

    // 取消生成
    if (cancelBtn) {
      cancelBtn.addEventListener('click', () => {
        if (isGenerating) {
          hideGenerateOutlineModal();
          flash('已取消大纲生成', 'info');
        }
      });
    }

    // 生成成功确定按钮
    if (successBtn) {
      successBtn.addEventListener('click', () => {
        hideGenerateSuccessModal();
      });
    }

    // 生成失败关闭按钮
    if (errorBtn) {
      errorBtn.addEventListener('click', () => {
        hideGenerateErrorModal();
      });
    }

    // 点击遮罩层关闭成功弹窗
    const successModal = document.getElementById('generate-success-overlay');
    if (successModal) {
      successModal.addEventListener('click', (e) => {
        if (e.target === successModal) {
          hideGenerateSuccessModal();
        }
      });
    }

    // 点击遮罩层关闭失败弹窗
    const errorModal = document.getElementById('generate-error-overlay');
    if (errorModal) {
      errorModal.addEventListener('click', (e) => {
        if (e.target === errorModal) {
          hideGenerateErrorModal();
        }
      });
    }
  };

  // 返回按钮
  const backLink = document.querySelector('.back-link');
  if (backLink) {
    backLink.addEventListener('click', go('/user/index'));
  }

  // 步骤条
  const stepsContainer = document.getElementById('steps-container');
  if (stepsContainer && window.StepsComponent) {
    window.StepsComponent.mount(stepsContainer, {
      active: 1,
      routes: {
        1: null,
        2: '/project_document/outline-confirm',
        3: '/project_document/writing-workspace',
        4: '/project_document/preview-review',
      },
      onCurrent: () => flash('当前已在 填写构想'),
    });
  }

  // 文件上传功能
  const fileGrid = document.getElementById('file-grid');
  const dropzone = document.getElementById('upload-dropzone');
  const fileInput = document.getElementById('file-input');

  // 获取文件图标
  const getFileIcon = (fileName) => {
    const ext = fileName.split('.').pop().toLowerCase();
    if (['doc', 'docx'].includes(ext)) {
      return '/static/project_document/images/common/icon-file-doc.png';
    } else if (['ppt', 'pptx'].includes(ext)) {
      return '/static/project_document/images/common/icon-file-ppt.png';
    } else if (ext === 'pdf') {
      return '/static/project_document/images/common/icon-file-pdf.png';
    } else {
      return '/static/project_document/images/common/icon-file-ppt.png';
    }
  };

  // 获取文件类型标签
  const getFileTypeLabel = (fileName) => {
    const ext = fileName.split('.').pop().toLowerCase();
    if (['ppt', 'pptx'].includes(ext)) {
      return 'PPT';
    } else if (['doc', 'docx'].includes(ext)) {
      return 'DOC';
    } else if (ext === 'pdf') {
      return 'PDF';
    } else {
      return 'FILE';
    }
  };

  // 创建上传中的文件卡片
  const createUploadingCard = (fileName, progress = 0) => {
    const card = document.createElement('div');
    card.className = 'flex-col items-center shrink-0 relative file-card file-card--uploading';
    card.innerHTML = `
      <div class="file-icon-container">
        <img class="file-icon" src="${getFileIcon(fileName)}" />
        <div class="upload-progress-ring"></div>
      </div>
      <span class="file-name">${fileName.length > 12 ? fileName.slice(0, 10) + '...' : fileName}</span>
      <span class="file-type">${getFileTypeLabel(fileName)}</span>
      <div class="file-progress">
        <div class="progress-bar">
          <div class="progress-fill" style="width: ${progress}%"></div>
        </div>
        <span class="progress-text">${progress}%</span>
      </div>
    `;
    card.dataset.fileName = fileName;
    return card;
  };

  // 创建成功上传的文件卡片
  const createSuccessCard = (fileInfo) => {
    const displayName = fileInfo.original_name || fileInfo.name;
    const card = document.createElement('div');
    card.className = 'flex-col items-center shrink-0 relative file-card file-card--success';
    card.innerHTML = `
      <div class="file-icon-container">
        <img class="file-icon" src="${getFileIcon(displayName)}" />
      </div>
      <span class="file-name" title="${displayName}">${displayName.length > 12 ? displayName.slice(0, 10) + '...' : displayName}</span>
      <span class="file-type">${getFileTypeLabel(displayName)}</span>
      <div class="file-size">${formatFileSize(fileInfo.size)}</div>
      <div class="file-action-group">
        <img class="file-action-icon download-btn" src="/static/project_document/images/common/icon-download.png" alt="下载" title="下载"/>
        <img class="file-action-icon delete-btn" src="/static/project_document/images/common/icon-delete.png" alt="删除" title="删除"/>
      </div>
    `;

    // 绑定事件
    const downloadBtn = card.querySelector('.download-btn');
    const deleteBtn = card.querySelector('.delete-btn');

    downloadBtn.addEventListener('click', () => {
      downloadFile(fileInfo);
    });

    deleteBtn.addEventListener('click', () => {
      showDeleteConfirm(fileInfo, card);
    });

    return card;
  };

  // 格式化文件大小
  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
  };

  // 下载文件
  const downloadFile = (fileInfo) => {
    const link = document.createElement('a');
    link.href = fileInfo.url;
    link.download = fileInfo.original_name || fileInfo.name;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  // 删除文件
  const deleteFile = async (fileInfo, cardElement) => {
    const fileName = fileInfo.original_name || fileInfo.name;

    try {
      const response = await fetch('/project_document/delete-file', {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': getCSRFToken()
        },
        body: JSON.stringify({
          file_path: fileInfo.file_path,
          url: fileInfo.url
        })
      });

      const result = await response.json();

      if (result.code === 200) {
        // 从DOM中移除卡片
        if (cardElement && cardElement.parentNode) {
          cardElement.parentNode.removeChild(cardElement);
        }

        // 从uploadedFiles数组中移除
        uploadedFiles = uploadedFiles.filter(file => file.file_path !== fileInfo.file_path);

        flash('文件删除成功', 'success');
      } else {
        flash(`删除失败: ${result.message}`, 'error');
      }
    } catch (error) {
      console.error('删除文件失败:', error);
      flash('删除失败，请稍后重试', 'error');
    }
  };

  // 真实文件上传到服务器
  const uploadFileToServer = async (file) => {
    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('/project_document/upload', {
        method: 'POST',
        body: formData,
        headers: {
          'X-CSRF-Token': getCSRFToken()
        }
      });

      const result = await response.json();

      if (result.code === 200) {
        return {
          success: true,
          data: result.data
        };
      } else {
        return {
          success: false,
          message: result.message
        };
      }
    } catch (error) {
      return {
        success: false,
        message: '网络错误，请稍后重试'
      };
    }
  };

  // 模拟上传进度（实际项目中应该使用真正的上传进度事件）
  const simulateUploadProgress = (card, file) => {
    let progress = 0;
    const progressFill = card.querySelector('.progress-fill');
    const progressText = card.querySelector('.progress-text');

    const interval = setInterval(() => {
      progress += Math.random() * 20 + 10;
      if (progress >= 100) {
        progress = 100;
        clearInterval(interval);
      }

      if (progressFill) progressFill.style.width = `${progress}%`;
      if (progressText) progressText.textContent = `${Math.round(progress)}%`;
    }, 200);

    return interval;
  };

  // 处理文件选择
  const handleFiles = async (files) => {
    Array.from(files).forEach(async (file) => {
      // 验证文件类型
      const validTypes = ['.ppt', '.pptx', '.doc', '.docx', '.pdf'];
      const ext = '.' + file.name.split('.').pop().toLowerCase();

      if (!validTypes.includes(ext)) {
        flash(`不支持的文件格式：${file.name}，仅支持PPT、Word、PDF文件`, 'error');
        return;
      }

      // 验证文件大小
      if (file.size > 100 * 1024 * 1024) {
        flash(`文件超过100M限制：${file.name}`, 'error');
        return;
      }

      // 创建上传中卡片
      const uploadingCard = createUploadingCard(file.name);
      fileGrid.insertBefore(uploadingCard, dropzone);

      // 开始模拟进度
      const progressInterval = simulateUploadProgress(uploadingCard, file);

      try {
        // 开始上传
        const uploadResult = await uploadFileToServer(file);

        // 清除进度模拟
        clearInterval(progressInterval);

        if (uploadResult.success) {
          const fileData = uploadResult.data;

          // 上传成功，移除上传中卡片，添加成功卡片
          uploadingCard.remove();

          // 创建成功卡片
          const fileInfo = {
            name: fileData.name,
            original_name: fileData.original_name,
            url: fileData.url,
            file_path: fileData.file_path,
            unique_name: fileData.unique_name,
            mimeType: fileData.mimeType,
            size: fileData.size
          };

          uploadedFiles.push(fileInfo);
          const successCard = createSuccessCard(fileInfo);
          fileGrid.insertBefore(successCard, dropzone);

          flash(`上传成功：${file.name}`, 'success');
        } else {
          // 上传失败
          clearInterval(progressInterval);
          uploadingCard.remove();
          flash(`上传失败：${uploadResult.message}`, 'error');
        }
      } catch (error) {
        // 网络错误或其他异常
        clearInterval(progressInterval);
        uploadingCard.remove();
        flash(`上传失败：${error.message}`, 'error');
      }
    });
  };

  // 绑定上传事件
  if (dropzone && fileInput) {
    // 点击上传
    dropzone.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', (e) => {
      if (e.target.files.length) {
        handleFiles(e.target.files);
        fileInput.value = '';
      }
    });

    // 拖拽上传
    dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = '#217efd';
      dropzone.style.backgroundColor = '#f0f7ff';
    });

    dropzone.addEventListener('dragleave', () => {
      dropzone.style.borderColor = '';
      dropzone.style.backgroundColor = '';
    });

    dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropzone.style.borderColor = '';
      dropzone.style.backgroundColor = '';

      if (e.dataTransfer.files.length) {
        handleFiles(e.dataTransfer.files);
      }
    });
  }

  // 初始化加载已有的文件
  const loadExistingFiles = async () => {
    try {
      const response = await fetch('/project_document/files', {
        method: 'GET',
        headers: {
          'X-CSRF-Token': getCSRFToken()
        }
      });

      const result = await response.json();

      if (result.code === 200 && result.data.length > 0) {
        result.data.forEach(fileInfo => {
          uploadedFiles.push(fileInfo);
          const successCard = createSuccessCard(fileInfo);
          fileGrid.insertBefore(successCard, dropzone);
        });
      }
    } catch (error) {
      console.error('加载已有文件失败:', error);
    }
  };

  // 页面加载时获取已有文件
  loadExistingFiles();

  // 富文本编辑器（简要构想）
  let editorInstance = null;
  if (window.wangEditor) {
    const { createEditor, createToolbar } = window.wangEditor;
    const editor = createEditor({
      selector: '#editor-idea',
      config: {
        placeholder: '对于这篇立项报告，您有些什么想法？',
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
          },
        },
      },
      mode: 'default',
    });
    createToolbar({
      editor,
      selector: '#tb-idea',
      config: {
        // 使用默认全量工具栏，展示完整表头
      },
      mode: 'default',
    });
    editorInstance = editor;
  }

  // 下一步按钮点击事件 - 调用生成大纲接口
  const nextButton = document.getElementById('next-button');
  if (nextButton) {
    nextButton.addEventListener('click', async () => {
      // 防止重复点击
      if (isGenerating) {
        return;
      }

      // 验证输入
      const titleInput = document.getElementById('title-input');
      const title = titleInput ? titleInput.value.trim() : '';

      let idea = '';
      let ideaTextForValidation = '';
      if (editorInstance) {
        // 修改：获取富文本HTML内容，而不是纯文本
        idea = editorInstance.getHtml() || '';

        // 修改：验证时去除HTML标签，检查是否有实际内容
        if (idea) {
          const tempDiv = document.createElement('div');
          tempDiv.innerHTML = idea;
          ideaTextForValidation = tempDiv.textContent || tempDiv.innerText || '';
        }
      }

      // 获取已上传的文件
      const attachments = getUploadedFiles();

      // 验证必填项
      let isValid = true;

      if (!title) {
        showError('title-error', '请输入产品立项报告名称');
        isValid = false;
      } else {
        hideError('title-error');
      }

      // 修改：验证时使用去除HTML标签后的纯文本
      if (!ideaTextForValidation.trim()) {
        showError('idea-error', '请输入简要构想');
        isValid = false;
      } else {
        hideError('idea-error');
      }

      if (!isValid) {
        flash('请填写所有必填项', 'error');
        return;
      }

      // 准备请求数据
      const requestData = {
        title: title,
        idea: idea, // 修改：这里发送富文本HTML内容
        attachments: attachments
      };

      console.log('提交数据:', {
        title: title,
        ideaLength: idea.length,
        attachmentsCount: attachments.length
      });

      // 显示生成大纲弹窗
      showGenerateOutlineModal();

      try {
        // 调用生成大纲接口
        const response = await fetch('/project_document/outline', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': getCSRFToken()
          },
          body: JSON.stringify(requestData)
        });

        const result = await response.json();

        console.log('生成大纲结果:', result);

        if (result.code === 200) {
          // 隐藏生成弹窗，显示成功弹窗
          hideGenerateOutlineModal();
          showGenerateSuccessModal();

          // 保存文档ID到localStorage，以便后续页面使用
          if (result.data && result.data.document_id) {
            localStorage.setItem('current_document_id', result.data.document_id);

            // 2秒后自动跳转
            setTimeout(() => {
              hideGenerateSuccessModal();
              window.location.href = `/project_document/outline-confirm/${result.data.document_id}`;
            }, 2000);
          } else {
            // 如果没有返回document_id，显示错误
            hideGenerateOutlineModal();
            showGenerateErrorModal('生成大纲失败：未返回文档ID');
          }
        } else {
          hideGenerateOutlineModal();
          showGenerateErrorModal(`生成大纲失败：${result.message || '未知错误'}`);
          console.error('大纲生成失败：', result);
        }
      } catch (error) {
        hideGenerateOutlineModal();
        showGenerateErrorModal(`网络错误：${error.message}`);
        console.error('请求失败：', error);
      }
    });
  }

  // 输入框实时验证
  const titleInput = document.getElementById('title-input');
  if (titleInput) {
    titleInput.addEventListener('input', () => {
      if (titleInput.value.trim()) {
        hideError('title-error');
      }
    });
  }

  // 编辑器内容变化验证
  if (editorInstance) {
    editorInstance.on('change', () => {
      // 修改：验证时去除HTML标签检查内容
      const htmlContent = editorInstance.getHtml() || '';
      let textContent = '';
      if (htmlContent) {
        const tempDiv = document.createElement('div');
        tempDiv.innerHTML = htmlContent;
        textContent = tempDiv.textContent || tempDiv.innerText || '';
      }
      if (textContent.trim()) {
        hideError('idea-error');
      }
    });
  }

  // 初始化删除确认对话框
  initDeleteConfirmDialog();

  // 初始化生成大纲弹窗事件
  initGenerateOutlineDialog();
});