// static/project_document/preview-review/index.js
document.addEventListener('DOMContentLoaded', function () {
  // 数据服务引用
  const DataService = window.ProjectDocumentService;

  // ==================== 全局变量 ====================
  var articleData = {
    title: '',
    wordCount: 0,
    chapters: [],
    isEditMode: false
  };

  var currentEditor = null;
  var currentEditingSectionId = null;
  var documentId = null;
  var allEditors = {};
  var timerInterval = null; // 计时器
  var timerSeconds = 0; // 计时秒数
  var isPolishing = false; // 标记是否正在润色中

  // ==================== 工具函数 ====================

  // Toast提示函数
  function flash(text, type = 'info') {
    const hint = document.createElement('div');
    hint.className = `toast-hint toast-${type}`;
    hint.innerText = text;

    // 添加到页面
    const container = document.getElementById('toast-container') || document.body;
    container.appendChild(hint);

    // 显示
    setTimeout(() => {
      hint.classList.add('show');
    }, 10);

    // 3秒后隐藏并移除
    setTimeout(() => {
      hint.classList.remove('show');
      setTimeout(() => {
        if (hint.parentNode) {
          hint.parentNode.removeChild(hint);
        }
      }, 200);
    }, 3000);
  }

  // 获取CSRF token
  function getCSRFToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.getAttribute('content') : '';
  }

  // 显示/隐藏加载状态
  function showLoading(show) {
    const loadingOverlay = document.getElementById('loading-overlay');
    if (show) {
      if (!loadingOverlay) {
        const loadingDiv = document.createElement('div');
        loadingDiv.id = 'loading-overlay';
        loadingDiv.className = 'loading-overlay';
        loadingDiv.innerHTML =
          '<div class="loading-spinner"></div>' +
          '<div class="loading-text">加载中...</div>';
        document.body.appendChild(loadingDiv);
      } else {
        loadingOverlay.style.display = 'flex';
      }
    } else if (loadingOverlay) {
      loadingOverlay.style.display = 'none';
    }
  }

  // 显示错误
  function showError(message) {
    flash(message, 'error');
  }

  // ==================== 计时器函数 ====================
  function startTimer() {
    timerSeconds = 0;
    stopTimer(); // 先停止现有的计时器

    const timerElement = document.querySelector('.review-waiting-time');
    if (!timerElement) return;

    timerElement.textContent = '00:00';

    timerInterval = setInterval(() => {
      timerSeconds++;
      const minutes = Math.floor(timerSeconds / 60);
      const seconds = timerSeconds % 60;
      timerElement.textContent =
        (minutes < 10 ? '0' + minutes : minutes) + ':' +
        (seconds < 10 ? '0' + seconds : seconds);
    }, 1000);
  }

  function stopTimer() {
    if (timerInterval) {
      clearInterval(timerInterval);
      timerInterval = null;
    }
  }

  // 格式化时间显示
  function formatTime(seconds) {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return (minutes < 10 ? '0' + minutes : minutes) + ':' +
           (remainingSeconds < 10 ? '0' + remainingSeconds : remainingSeconds);
  }

  // ==================== 全文AI润色相关函数 ====================

  // 显示全文润色确认弹窗
  function showPolishConfirmModal() {
    const modal = document.getElementById('regenerate-confirm-overlay');
    const title = document.getElementById('regenerate-confirm-modal-title');
    const waitingArea = document.getElementById('waitingArea');

    if (modal && title && waitingArea) {
      // 重置弹窗状态
      title.textContent = '将对全文进行AI润色生成新的正文，是否继续？';
      waitingArea.style.display = 'none';
      modal.classList.add('show');

      // 重置按钮状态
      const cancelBtn = document.getElementById('regenerate-confirm-cancel');
      const continueBtn = document.getElementById('regenerate-confirm-continue');

      if (cancelBtn && continueBtn) {
        // 移除之前的事件监听器（通过克隆替换）
        const newCancelBtn = cancelBtn.cloneNode(true);
        const newContinueBtn = continueBtn.cloneNode(true);

        cancelBtn.parentNode.replaceChild(newCancelBtn, cancelBtn);
        continueBtn.parentNode.replaceChild(newContinueBtn, continueBtn);

        // 绑定新的事件
        newCancelBtn.addEventListener('click', hidePolishConfirmModal);
        newContinueBtn.addEventListener('click', handlePolishContinue);
      }

      // 绑定遮罩层点击事件
      modal.removeEventListener('click', handleModalClick);
      modal.addEventListener('click', handleModalClick);
    }
  }

  // 遮罩层点击事件处理
  function handleModalClick(e) {
    if (e.target === e.currentTarget && !isPolishing) {
      hidePolishConfirmModal();
      flash('已取消润色操作');
    }
  }

  // 隐藏全文润色确认弹窗
  function hidePolishConfirmModal() {
    const modal = document.getElementById('regenerate-confirm-overlay');
    if (modal) {
      modal.classList.remove('show');
      modal.removeEventListener('click', handleModalClick);
      stopTimer();
      isPolishing = false;
    }
  }

  // 显示等待区域
  function showWaitingArea() {
    const waitingArea = document.getElementById('waitingArea');
    const title = document.getElementById('regenerate-confirm-modal-title');
    const buttons = document.querySelector('.unmerged-modal-buttons');

    if (waitingArea && title && buttons) {
      waitingArea.style.display = 'block';
      title.textContent = 'AI正在润色全文，请耐心等待...';
      buttons.style.display = 'none'; // 隐藏按钮
      startTimer();
    }
  }

  // 显示润色成功状态
  function showPolishSuccess() {
    const waitingArea = document.getElementById('waitingArea');
    if (waitingArea) {
      waitingArea.innerHTML = `
        <div class="review-waiting-content">
          <span class="review-waiting-time" style="color: #52c41a;">✓</span>
          <div class="review-waiting-text">
            <span style="color: #52c41a;">润色成功！即将跳转到对比页面...</span>
          </div>
        </div>
      `;
    }
  }

  // 显示润色错误状态
  function showPolishError(errorMessage) {
    const waitingArea = document.getElementById('waitingArea');
    if (waitingArea) {
      waitingArea.innerHTML = `
        <div class="review-waiting-content">
          <span class="review-waiting-time" style="color: #ff4d4f;">✗</span>
          <div class="review-waiting-text">
            <span style="color: #ff4d4f;">润色失败: ${errorMessage}</span>
            <div style="margin-top: 10px;">
              <button class="polish-retry-btn btn btn-primary" id="polish-retry-btn">重试</button>
              <button class="polish-cancel-btn btn btn-secondary" id="polish-cancel-btn">取消</button>
            </div>
          </div>
        </div>
      `;

      // 绑定重试按钮事件
      const retryBtn = document.getElementById('polish-retry-btn');
      const cancelBtn = document.getElementById('polish-cancel-btn');

      if (retryBtn) {
        retryBtn.addEventListener('click', () => {
          handlePolishContinue();
        });
      }

      if (cancelBtn) {
        cancelBtn.addEventListener('click', () => {
          hidePolishConfirmModal();
        });
      }
    }
  }

  // 处理继续按钮点击
  async function handlePolishContinue() {
    if (isPolishing) return;

    try {
      isPolishing = true;
      // 显示等待区域
      showWaitingArea();

      // 调用全文润色接口
      const result = await DataService.polishFullDocument(documentId);

      // 停止计时器
      stopTimer();

      // 检查结果
      if (result && result.newFullText && result.newFullText.length > 0) {
        const treeData = result.newFullText; // 获取润色后的全文数据

        // 显示成功提示
        showPolishSuccess();
        flash('全文润色完成，即将跳转到对比页面');

        // 延时后跳转
        setTimeout(() => {
          // 使用DataService.navigateToPage跳转到对比页面
          DataService.navigateToPage(`/project_document/full-compare/${documentId}`, {
            document_id: documentId,
            tree_data: treeData,
            node_id: 'all',
            source: 'polish'
          });
        }, 2000);

      } else {
        // 处理空结果
        showPolishError('未返回有效的文本内容');
        isPolishing = false;
      }

    } catch (error) {
      // 停止计时器
      stopTimer();

      // 显示错误信息
      console.error('全文AI润色失败:', error);
      showPolishError(error.message || '未知错误');
      isPolishing = false;
    }
  }

  // ==================== 初始化函数 ====================
  function init() {
    // 从URL获取文档ID
    var pathParts = window.location.pathname.split('/');
    for (var i = 0; i < pathParts.length; i++) {
      if (pathParts[i] === 'preview-review' && i + 1 < pathParts.length) {
        documentId = parseInt(pathParts[i + 1]);
        break;
      }
    }

    if (!documentId || isNaN(documentId)) {
      console.error('无法获取文档ID');
      showError('文档ID无效');
      return;
    }

    // 检查URL参数
    var urlParams = new URLSearchParams(window.location.search);
    var modeParam = urlParams.get('mode');
    articleData.isEditMode = modeParam === 'edit';

    // 加载文章数据
    loadArticleData();

    // 绑定事件
    bindEvents();

    // 初始化滚动条相关事件
    initScrollHandlers();
  }

  // ==================== 滚动条事件处理 ====================
  function initScrollHandlers() {
    // 监听主滚动区域的滚动事件
    const scrollArea = document.querySelector('.scrollable-content-area');
    if (scrollArea) {
      scrollArea.addEventListener('scroll', function() {
        // 可以在这里添加滚动时的处理逻辑
        // 例如：检测滚动到底部等
      });
    }
  }

  // ==================== 数据加载函数 ====================
  function loadArticleData() {
    showLoading(true);

    fetch(`/project_document/${documentId}/preview-data`, {
      method: 'GET',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': getCSRFToken()
      }
    })
    .then(response => response.json())
    .then(result => {
      showLoading(false);

      if (result.code === 200) {
        // 转换数据结构
        articleData.title = result.data.title || '未命名文档';
        articleData.wordCount = result.data.wordCount || 0;
        articleData.chapters = transformChaptersData(result.data.chapters);

        // 渲染页面
        renderPage();

        // 如果是编辑模式，初始化编辑器
        if (articleData.isEditMode) {
          setTimeout(initEditors, 100);
        }
      } else {
        showError(result.message || '加载失败');
      }
    })
    .catch(error => {
      showLoading(false);
      console.error('加载数据失败:', error);
      showError('网络错误，请稍后重试');
    });
  }

  // ==================== 数据转换函数 ====================
  function transformChaptersData(backendChapters) {
    return backendChapters.map(chapter => {
      return {
        name: chapter.name || `第${chapter.node_id}章`,
        title: chapter.title || '',
        sections: chapter.sections.map(section => {
          return {
            id: section.id,
            title: section.title || '无标题',
            content: section.content || '暂无内容',
            key_point: section.key_point,
            review_score: section.review_score,
            review_detail: section.review_detail
          };
        })
      };
    });
  }

  // ==================== 页面渲染函数 ====================
  function renderPage() {
    // 1. 设置文章基本信息
    document.getElementById('article-title').textContent = articleData.title;
    document.getElementById('article-word-count').textContent = `全文共${articleData.wordCount}字`;

    // 2. 渲染顶部按钮（编辑/保存/取消）
    renderTopButtons();

    // 3. 渲染章节列表
    var chaptersHtml = '';
    for (var i = 0; i < articleData.chapters.length; i++) {
      var chapter = articleData.chapters[i];
      var chapterMarginTop = (i === 0) ? '1.5rem' : '2.5rem';

      chaptersHtml +=
        '<div class="flex-col self-stretch group-chapter" style="margin-top: ' + chapterMarginTop + ';">' +
        '<div class="flex-row">' +
        '<span class="font-chapter-num text-gradient text-chapter-margin">' + chapter.name + '</span>' +
        '<span class="font-chapter-title ml-space-fifteen">' + chapter.title + '</span>' +
        '</div>' +
        '<div class="mt-space-twenty-two flex-row relative group-chapter-content">' +
        '<div class="chapter-sections">' +
        renderSections(chapter.sections) +
        '</div>' +
        '<img class="img-content-bg pos-content-bg" src="/static/project_document/images/common/bg-content.png" />' +
        '</div>' +
        '</div>';
    }
    document.getElementById('chapters-container').innerHTML = chaptersHtml;

    // 4. 挂载步骤条
    if (window.StepsComponent) {
      StepsComponent.mount(document.getElementById('steps-container'), {
        active: 4,
        routes: {
          1: `/project_document/outline-draft`,
          2: `/project_document/outline-confirm/${documentId}`,
          3: `/project_document/writing-workspace/${documentId}`,
          4: null,
        },
        onCurrent: function () { }
      });
    }

    // 5. 调整章节容器高度
    adjustChaptersContainerHeight();
  }

  // 调整章节容器高度
  function adjustChaptersContainerHeight() {
    const chaptersContainer = document.getElementById('chapters-container');
    if (chaptersContainer) {
      // 根据内容动态调整最小高度
      const chapterElements = chaptersContainer.querySelectorAll('.group-chapter');
      if (chapterElements.length > 0) {
        // 确保有足够的最小高度以显示内容
        chaptersContainer.style.minHeight = 'calc(100vh - 300px)';
      }
    }
  }

  function renderSections(sections) {
    var sectionsHtml = '';
    for (var j = 0; j < sections.length; j++) {
      var section = sections[j];
      var sectionMarginTop = (j === 0) ? '1.86rem' : '3rem';
      var safeId = section.id.replace(/\./g, '_');

      if (articleData.isEditMode) {
        // 编辑模式的HTML - 使用富文本编辑器
        sectionsHtml +=
          '<div class="section-wrapper" data-section-id="' + section.id + '" style="margin-top: ' + sectionMarginTop + ';">' +
          '<div class="section-editor-inline">' +
          '<div class="section-editor-header">' +
          '<img class="img-header-bg" src="/static/project_document/images/preview-review/bg-header.png" />' +
          '<span class="font-btn text-editor-title">' + section.id + ' ' + section.title + '</span>' +
          '</div>' +
          '<div class="editor-body">' +
          '<div class="writing-toolbar"><div id="writer-toolbar-' + safeId + '"></div></div>' +
          '<div id="editor-content-' + safeId + '" class="editor-content-area"></div>' +
          '</div>' +
          '</div>' +
          '</div>';
      } else {
        // 预览模式的HTML - 直接显示富文本内容
        var editIconHtml = articleData.isEditMode ?
          '<img class="img-icon btn-edit-icon" src="/static/project_document/images/preview-review/icon-checklist.png" style="cursor: pointer;" data-id="' + section.id + '" />' : '';

        // 添加评审分数显示
        var reviewHtml = '';
        if (section.review_score !== null && section.review_score !== undefined) {
          reviewHtml = '<div class="review-info">评分: ' + section.review_score + '/10</div>';
        }

        sectionsHtml +=
          '<div class="section-wrapper" data-section-id="' + section.id + '" style="margin-top: ' + sectionMarginTop + ';">' +
          '<div class="section-row">' +
          '<span class="font-section-num text-gradient">' + section.id + '</span>' +
          '<span class="font-section-title">' + section.title + '</span>' +
          editIconHtml +
          '</div>' +
          reviewHtml +
          '<div class="font-content text-content-full section-content" style="display: block; margin-top: 1rem;">' +
          (section.content || '暂无内容') +
          '</div>' +
          '</div>';
      }
    }
    return sectionsHtml;
  }

  function renderTopButtons() {
    var container = document.getElementById('edit-action-container');

    if (articleData.isEditMode) {
      container.innerHTML =
        '<div class="flex-row items-center justify-center action-buttons-container" style="margin-top: 1rem; gap: 1rem;">' +
        '<div class="btn-cancel-edit" id="btn-cancel-all"><span class="font-btn">取消</span></div>' +
        '<div class="btn-save-edit" id="btn-save-all"><span class="font-btn">保存</span></div>' +
        '</div>';
      container.style.display = 'block';
    } else {
      container.innerHTML =
        '<div class="flex-row items-center justify-center action-buttons-container" style="margin-top: 1rem;">' +
        '<div class="btn-edit-all" id="btn-edit-all"><span class="font-btn">编辑</span></div>' +
        '</div>';
      container.style.display = 'block';
    }
  }

  // ==================== 编辑器相关函数 ====================
  async function initEditors() {
    if (!window.TiptapEditorFactory) {
      console.error('TiptapEditorFactory未加载');
      return;
    }

    allEditors = {};

    for (var i = 0; i < articleData.chapters.length; i++) {
      var chapter = articleData.chapters[i];
      for (var j = 0; j < chapter.sections.length; j++) {
        var section = chapter.sections[j];
        var safeId = section.id.replace(/\./g, '_');

        try {
          // 创建编辑器实例
          var editor = await window.TiptapEditorFactory.createEditor({
            selector: '#editor-content-' + safeId,
            toolbarSelector: '#writer-toolbar-' + safeId
          });
          editor.setHtml(section.content || '<p></p>');

          allEditors[section.id] = editor;
        } catch (e) {
          console.error('编辑器加载失败:', e);
        }
      }
    }
  }

  async function openSingleEditor(sectionId, content) {
    closeSingleEditor();

    var wrapper = document.querySelector('.section-wrapper[data-section-id="' + sectionId + '"]');
    if (!wrapper) return;

    var editorDiv = document.createElement('div');
    editorDiv.id = 'single-editor-box';
    editorDiv.className = 'section-editor';
    editorDiv.innerHTML =
      '<div class="section-editor-header">' +
      '<img class="img-header-bg" src="/static/project_document/images/preview-review/bg-header.png" />' +
      '<span class="font-btn text-editor-title">编辑小节内容</span>' +
      '<div class="editor-header-actions">' +
      '<div class="btn-cancel" id="btn-cancel-single"><span class="font-btn text-cancel">取消</span></div>' +
      '<div class="btn-save" id="btn-save-single"><span class="font-btn text-save">保存</span></div>' +
      '</div>' +
      '</div>' +
      '<div class="editor-body">' +
      '<div class="writing-toolbar"><div id="single-toolbar"></div></div>' +
      '<div id="single-content"></div>' +
      '</div>';

    wrapper.appendChild(editorDiv);

    if (window.TiptapEditorFactory) {
      currentEditor = await window.TiptapEditorFactory.createEditor({
        selector: '#single-content',
        toolbarSelector: '#single-toolbar'
      });
      currentEditor.setHtml(content || '<p></p>');

      currentEditingSectionId = sectionId;
    }

    // 滚动到编辑器位置
    setTimeout(() => {
      editorDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 100);
  }

  function closeSingleEditor() {
    var box = document.getElementById('single-editor-box');
    if (box) box.remove();
    if (currentEditor) {
      currentEditor.destroy();
      currentEditor = null;
    }
    currentEditingSectionId = null;
  }

  // ==================== 数据保存函数 ====================
  function saveSectionContent(sectionId, content) {
    showLoading(true);

    return fetch(`/project_document/${documentId}/section-content`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRF-Token': getCSRFToken()
      },
      body: JSON.stringify({
        section_id: sectionId,
        content: content
      })
    })
    .then(response => response.json())
    .then(result => {
      showLoading(false);
      if (result.code === 200) {
        return { success: true, message: result.message };
      } else {
        return { success: false, message: result.message };
      }
    })
    .catch(error => {
      showLoading(false);
      console.error('保存失败:', error);
      return { success: false, message: '网络错误' };
    });
  }

  function saveAllSections() {
    if (!allEditors || Object.keys(allEditors).length === 0) {
      flash('没有可保存的内容', 'info');
      return;
    }

    showLoading(true);

    var promises = [];
    for (var key in allEditors) {
      var editor = allEditors[key];
      var content = editor.getHtml().trim();
      if (content && content !== '<p></p>') {
        promises.push(saveSectionContent(key, content));
      }
    }

    if (promises.length === 0) {
      showLoading(false);
      flash('没有修改的内容需要保存', 'info');
      return;
    }

    Promise.all(promises)
      .then(results => {
        var successCount = results.filter(r => r.success).length;
        if (successCount === results.length) {
          flash('所有内容保存成功！', 'success');
          // 重新加载数据
          setTimeout(() => {
            loadArticleData();
          }, 1000);
        } else {
          flash('部分内容保存失败，请重试', 'error');
        }
      })
      .finally(() => {
        showLoading(false);
      });
  }

  // ==================== 工具函数 ====================
  function getSectionContent(sectionId) {
    for (var i = 0; i < articleData.chapters.length; i++) {
      var chapter = articleData.chapters[i];
      for (var j = 0; j < chapter.sections.length; j++) {
        if (chapter.sections[j].id === sectionId) {
          return chapter.sections[j].content || '';
        }
      }
    }
    return '';
  }

  function updateSectionContent(sectionId, newContent) {
    for (var i = 0; i < articleData.chapters.length; i++) {
      var chapter = articleData.chapters[i];
      for (var j = 0; j < chapter.sections.length; j++) {
        if (chapter.sections[j].id === sectionId) {
          chapter.sections[j].content = newContent;
          return true;
        }
      }
    }
    return false;
  }

  function setEditMode(isEditMode) {
    articleData.isEditMode = isEditMode;
    var url = new URL(window.location);
    if (isEditMode) {
      url.searchParams.set('mode', 'edit');
    } else {
      url.searchParams.delete('mode');
    }
    window.history.replaceState({}, '', url);
    renderPage();
    if (isEditMode) {
      setTimeout(initEditors, 100);
    }
  }

  // ==================== 事件绑定函数 ====================
  function bindEvents() {
    document.addEventListener('click', function (e) {
      var id = e.target.id;
      var target = e.target;

      // 分享功能
      if (id === 'btn-share' || target.closest('#btn-share')) {
        sharePage();
        return;
      }

      // 下载功能
      if (id === 'btn-download' || target.closest('#btn-download')) {
        downloadArticle();
        return;
      }

      // 全文AI润色 - 修改部分
      if (id === 'btn-polish' || target.closest('#btn-polish')) {
        // 显示确认弹窗
        showPolishConfirmModal();
        return;
      }

      // 返回智能写作
      if (id === 'btn-back-writing' || target.closest('#btn-back-writing')) {
        window.location.href = `/project_document/writing-workspace/${documentId}`;
        return;
      }

      // 编辑全部
      if (id === 'btn-edit-all' || target.closest('#btn-edit-all')) {
        setEditMode(true);
        return;
      }

      // 取消全部
      if (id === 'btn-cancel-all' || target.closest('#btn-cancel-all')) {
        setEditMode(false);
        return;
      }

      // 保存全部
      if (id === 'btn-save-all' || target.closest('#btn-save-all')) {
        saveAllSections();
        return;
      }

      // 点击单个编辑图标
      if (target.classList.contains('btn-edit-icon')) {
        var sectionId = target.getAttribute('data-id');
        if (currentEditingSectionId === sectionId) {
          closeSingleEditor();
        } else {
          var content = getSectionContent(sectionId);
          openSingleEditor(sectionId, content);
        }
        return;
      }

      // 单个取消
      if (id === 'btn-cancel-single' || target.closest('#btn-cancel-single')) {
        closeSingleEditor();
        return;
      }

      // 单个保存
      if (id === 'btn-save-single' || target.closest('#btn-save-single')) {
        if (currentEditor) {
          var content = currentEditor.getHtml().trim();
          if (!content || content === '<p></p>') {
            flash('请输入内容', 'error');
            return;
          }

          saveSectionContent(currentEditingSectionId, content)
            .then(result => {
              if (result.success) {
                updateSectionContent(currentEditingSectionId, content);
                closeSingleEditor();
                flash('保存成功！', 'success');
                // 更新预览显示
                var sectionElement = document.querySelector('.section-wrapper[data-section-id="' + currentEditingSectionId + '"] .section-content');
                if (sectionElement) {
                  sectionElement.innerHTML = content;
                }
              } else {
                flash('保存失败: ' + result.message, 'error');
              }
            });
        }
        return;
      }

      // 返回首页
      if (target.classList.contains('text-back-home')) {
        window.location.href = '/';
      }
    });
  }

  function sharePage() {
    var shareUrl = window.location.href;
    var title = articleData.title || '全文预览';

    if (navigator.share) {
      navigator.share({ title: title, url: shareUrl }).catch(function () { });
      return;
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(shareUrl).then(function () {
        flash('链接已复制到剪贴板', 'success');
      });
      return;
    }

    var input = document.createElement('input');
    input.value = shareUrl;
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    document.body.removeChild(input);
    flash('链接已复制到剪贴板', 'success');
  }

  function downloadArticle() {
    var text = buildArticleText();
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var link = document.createElement('a');
    var title = (articleData.title || 'preview-review').replace(/[\\/:*?"<>|]+/g, '_');
    link.href = URL.createObjectURL(blob);
    link.download = title + '.txt';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
    flash('文档下载成功', 'success');
  }

  function buildArticleText() {
    var lines = [];
    if (articleData.title) {
      lines.push(articleData.title);
    }
    if (articleData.wordCount) {
      lines.push('全文共' + articleData.wordCount + '字');
    }

    for (var i = 0; i < articleData.chapters.length; i++) {
      var chapter = articleData.chapters[i];
      lines.push('');
      lines.push(chapter.name + ' ' + chapter.title);

      for (var j = 0; j < chapter.sections.length; j++) {
        var section = chapter.sections[j];
        lines.push('');
        lines.push(section.id + ' ' + section.title);

        // 移除HTML标签，只保留纯文本
        var tempDiv = document.createElement('div');
        tempDiv.innerHTML = section.content || '';
        var plainText = tempDiv.textContent || tempDiv.innerText || '';
        lines.push(plainText);
      }
    }

    return lines.join('\n');
  }

  // ==================== 初始化 ====================
  init();
});