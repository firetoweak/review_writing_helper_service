// static/project_document/preview-review/index.js
document.addEventListener('DOMContentLoaded', function () {
  // ==================== 全局变量 ====================
  var articleData = {
    title: '',
    valData:[],
    total_score:0,
    total_content:""
  };

  var currentEditor = null;
  var currentEditingSectionId = null;
  var documentId = null;
  var allEditors = {};

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

  // ==================== 初始化函数 ====================
  function init() {
    // 从URL获取文档ID
    var pathParts = window.location.pathname.split('/');
    for (var i = 0; i < pathParts.length; i++) {
      if (pathParts[i] === 'full-text-review' && i + 1 < pathParts.length) {
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

    fetch(`/project_document/${documentId}/full-text-data`, {
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
        articleData.title = result.data.title ;
        articleData.valData = result.data.steps;
        articleData.total_score = result.data.total_review_score
        articleData.total_content = result.data.total_review_content
        // 渲染页面
        renderPage();
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
    document.getElementById('article-title').innerHTML = `${articleData.title}`;
    var html = ""
    let all_score = {}
    for(let key in articleData.valData){
        var content = `
        <div style="margin: 0 auto;float: left;width: 100%">
          <div class="title_score">
                <div class="title">${articleData.valData[key].chapter_title}:</div>
                <div class="score">
                    ${articleData.valData[key].review_score}分/(满分10分)
                </div>
          </div>
          <div class="evaluate">
            从${articleData.valData[key].chapter_title}商业价值，<span>${articleData.valData[key].evaluate}</span>
          </div>
           <div class="suggestion">
            改进建议:<span>${articleData.valData[key].suggestion}</span>
          </div>
      </div>
        `
        html = html+content
        all_score[articleData.valData[key].chapter_title] = articleData.valData[key].review_score
    }
    console.log(all_score)
    $('#chapters-container').after(html)
    $('#total_score').html(articleData.total_score)
    html = `
    <div style="margin: 0 auto;float: left;width: 100%">
          <div class="title_score">
                <div class="title">下一步建议:</div>
          </div>
           <div class="suggestion">
            改进建议:<span>${articleData.total_content}</span>
          </div>
      </div>
    `
    $('.footer-brand').before(html)
var myChart = echarts.init(document.getElementById('chapters-container'));
var option = {
  radar: {
    indicator: [
      { name: "投资收益视角", max: 10 },
      { name: "机会识别视角", max: 10 },
      { name: "产品包定义视角", max: 10 },
      { name: "路径与壁垒视角", max: 10 },
      { name: "产品定位视角", max: 10 },
    ],
    center: ['50%', '50%'],
    radius: '80%',
    splitNumber: 4,
    splitArea: {
      areaStyle: {
         color: [
          'rgba(240, 249, 232, 0.6)', // 最内层浅色
          'rgba(200, 230, 255, 0.6)', // 第二层浅蓝
          'rgba(150, 200, 255, 0.6)', // 第三层中蓝
          'rgba(100, 181, 246, 0.6)'  // 最外层蓝色（大五边形）
        ]
      }
    },
    axisLine: { lineStyle: { color: '#999' } },
    // 关闭radar层面的pointLabels，改用series.label
    pointLabels: {
      show: false // 关键：关闭原生标签
    }
  },
  series: [
    {
      type: 'radar',
      data: [
        {
          value: [all_score['投资收益视角'],all_score['机会识别视角'],all_score['产品包定义视角'],all_score['路径与壁垒视角'],all_score['产品定位视角']],
          areaStyle: { color:  'rgba(145, 223, 145, 0.6)' },
        }
      ],
      // 核心：用series.label实现自定义标签（100%生效）
      label: {
        show: true,
        position: 'outside', // 标签显示在雷达图外侧
        distance: 10, // 标签与顶点的距离
        formatter: function(params) {
          // params.name 就是indicator里的名称（如"投资收益视角"）
          return `${params.name}`+ '\n'+params.value+"分"; // 拼接换行的分数
        },
        fontSize: 12,
        lineHeight: 20,
        align: 'center',
        verticalAlign: 'middle',
        width: 100,
        height: 40
      },
      // 确保顶点标记显示（可选，方便定位）
      symbol: 'circle',
      symbolSize: 4
    }
  ]
};



// 渲染图表
myChart.setOption(option);






        // 4. 挂载步骤条
    if (window.StepsComponent) {
      StepsComponent.mount(document.getElementById('steps-container'), {
        active: 5,
        routes: {
          1: `/project_document/outline-draft`,
          2: `/project_document/outline-confirm/${documentId}`,
          3: `/project_document/writing-workspace/${documentId}`,
          4: null,
          5:null,
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
  function initEditors() {
    if (!window.wangEditor) {
      console.error('wangEditor未加载');
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
          var editor = window.wangEditor.createEditor({
            selector: '#editor-content-' + safeId,
            html: section.content || '<p></p>',
            config: {
              placeholder: '请输入内容...',
              MENU_CONF: {
                uploadImage: {
                  server: '/user/aiVal/upload_pic', // 图片上传接口
                  fieldName: 'file',
                  maxFileSize: 5 * 1024 * 1024, // 5MB
                  maxNumberOfFiles: 5, // 最多上传5张图片
                  headers: {
                    'X-CSRF-Token': getCSRFToken()
                  },
                  customInsert: function (res, insertFn) {
                    if (res.code == 1 || res.code === 200) {
                      insertFn(res.url || res.data.url); // 插入图片URL
                    } else {
                      flash(res.msg || '上传失败', 'error');
                    }
                  }
                }
              }
            },
            mode: 'default'
          });

          // 创建工具栏
          window.wangEditor.createToolbar({
            editor: editor,
            selector: '#writer-toolbar-' + safeId,
            config: {
              excludeKeys: [
                'group-video',
                'fullScreen'
              ]
            },
            mode: 'default'
          });

          allEditors[section.id] = editor;
        } catch (e) {
          console.error('编辑器加载失败:', e);
        }
      }
    }
  }

  function openSingleEditor(sectionId, content) {
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

    if (window.wangEditor) {
      currentEditor = window.wangEditor.createEditor({
        selector: '#single-content',
        html: content || '<p></p>',
        config: {
          placeholder: '请输入内容...',
          MENU_CONF: {
            uploadImage: {
              server: '/user/aiVal/upload_pic', // 图片上传接口
              fieldName: 'file',
              maxFileSize: 5 * 1024 * 1024, // 5MB
              maxNumberOfFiles: 5, // 最多上传5张图片
              headers: {
                'X-CSRF-Token': getCSRFToken()
              },
              customInsert: function (res, insertFn) {
                if (res.code == 1 || res.code === 200) {
                  insertFn(res.url || res.data.url); // 插入图片URL
                } else {
                  flash(res.msg || '上传失败', 'error');
                }
              }
            }
          }
        },
        mode: 'default'
      });

      window.wangEditor.createToolbar({
        editor: currentEditor,
        selector: '#single-toolbar',
        config: {
          excludeKeys: [
            'group-video',
            'fullScreen'
          ]
        },
        mode: 'default'
      });

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

      // 全文AI润色
      if (id === 'btn-polish' || target.closest('#btn-polish')) {
        window.location.href = `/project_document/full-compare/${documentId}`;
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