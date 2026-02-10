 const createUploadingCard = (fileName, progress = 0) => {
        const card = document.createElement('div');
        card.className = 'material-grid-item';
        card.innerHTML = `
          <div class="file-icon-container">
            <img class="material-file-icon" src="${getFileIcon(fileName)}" />
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
        console.log(card)
        return card;
      }
      const simulateUploadProgress = (card, file) => {
                        let progress = 0;
                        const progressFill = card.querySelector('.progress-fill');
                        const progressText = card.querySelector('.progress-text');

                        const interval = setInterval(() => {
                          progress += Math.random() * 20 + 10;
                          if (progress >= 100) {
                            progress = 99;
                            clearInterval(interval);
                          }

                          if (progressFill) progressFill.style.width = `${progress}%`;
                          if (progressText) progressText.textContent = `${Math.round(progress)}%`;
                        }, 200);
                        return interval;
      }
        const uploadFileToServer = async (file,documentId) => {
                const formData = new FormData();
                formData.append('file', file);
                try {
                  const response = await fetch('/project_document/'+documentId+'/material_upload', {
                    method: 'POST',
                    body: formData,
                    headers: {
                      'X-CSRF-Token':""
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
          const downloadFile = (fileInfo) => {
            const link = document.createElement('a');
            link.href = fileInfo.url;
            link.download = fileInfo.original_name || fileInfo.name;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        };
          const downloadFileUrl = (file_url,file_name) => {
            const link = document.createElement('a');
            link.href = file_url;
            link.download = file_name;
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);
        };

        const createSuccessCard = (fileInfo) => {
                const displayName = fileInfo.original_name || fileInfo.name;
                const card = document.createElement('div');
                card.className = 'material-grid-item';
                card.innerHTML = `
                  <div class="file-icon-container">
                    <img class="material-file-icon" src="${getFileIcon(displayName)}" />
                  </div>
                  <span class="file-name" title="${displayName}">${displayName.length > 12 ? displayName.slice(0, 10) + '...' : displayName}</span>
                  <span class="file-type">${getFileTypeLabel(displayName)}</span>
                  <div class="file-size">${formatFileSize(fileInfo.size)}</div>
                  <div class="file-action-group">
                    <img class="material-action-icon material-download-btn" src="/static/project_document/images/common/icon-download.png" alt="下载" title="下载"/>
                    <img class="material-action-icon material-delete-btn" src="/static/project_document/images/common/icon-delete.png" alt="删除" title="删除"/>
                  </div>
                `;
                // 绑定事件
                const downloadBtn = card.querySelector('.material-download-btn');
                const deleteBtn = card.querySelector('.material-delete-btn');

                downloadBtn.addEventListener('click', () => {
                  downloadFile(fileInfo);
                });

                deleteBtn.addEventListener('click', () => {
                  showDeleteConfirm(fileInfo, card);
                });

                return card;
        };

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



          const formatFileSize = (bytes) => {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
          };
      function getFileIcon(fileName) {
        const ext = fileName.split('.').pop().toLowerCase();
        const iconMap = {
            'pdf': '/static/project_document/images/common/icon-file-pdf.png',
            'doc': '/static/project_document/images/common/icon-file-doc.png',
            'docx': '/static/project_document/images/common/icon-file-doc.png',
            'ppt': '/static/project_document/images/common/icon-file-ppt.png',
            'pptx': '/static/project_document/images/common/icon-file-ppt.png',
            'xls': '/static/project_document/images/common/icon-file-xls.png',
            'xlsx': '/static/project_document/images/common/icon-file-xls.png',
            'jpg': '/static/project_document/images/common/icon-file-image.png',
            'jpeg': '/static/project_document/images/common/icon-file-image.png',
            'png': '/static/project_document/images/common/icon-file-image.png',
            'gif': '/static/project_document/images/common/icon-file-image.png'
        };

        return iconMap[ext] || '/static/project_document/images/common/icon-file-doc.png';
    }

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
