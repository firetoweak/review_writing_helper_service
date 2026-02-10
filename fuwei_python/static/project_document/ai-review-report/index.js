document.addEventListener('DOMContentLoaded', function () {
  // ==================== 数据定义 ====================
  var articleData = (window.MockData && window.MockData.articleData) || { title: '', wordCount: 0, chapters: [], isEditMode: false };
  var urlParams = new URLSearchParams(window.location.search);
  var modeParam = urlParams.get('mode');
  var allowEditControls = modeParam === 'editable';
  if (modeParam === 'edit') {
    articleData.isEditMode = true;
  }

  var currentEditor = null;
  var currentEditingSectionId = null;

  // ==================== 页面渲染函数 ====================

  // 渲染整个文章页面
  function renderPage() {
    // 1. 设置文章基本信息
    document.getElementById('article-title').innerHTML = articleData.title;
    document.getElementById('article-word-count').innerHTML = '全文共' + articleData.wordCount + '字';

    // 2. 渲染章节列表
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

    // 3. 渲染底部按钮
    renderBottomButtons();

    // 4. 挂载步骤条
    var stepsContainer = document.getElementById('steps-container');
    if (window.StepsComponent && stepsContainer) {
      StepsComponent.mount(stepsContainer, {
        active: 4,
        routes: {
          1: '../outline-draft/index.html',
          2: '../outline-confirm/index.html',
          3: '../writing-workspace/index.html',
          4: null,
        },
        onCurrent: function () { }
      });
    }

    // 5. 如果是编辑模式，初始化编辑器
    if (articleData.isEditMode) {
      setTimeout(function () {
        initEditors();
      }, 100);
    }
  }

  // 渲染小节列表
  function renderSections(sections) {
    var sectionsHtml = '';
    for (var j = 0; j < sections.length; j++) {
      var section = sections[j];
      var sectionMarginTop = (j === 0) ? '1.86rem' : '3rem';
      var safeId = section.id.replace(/\./g, '_');

      if (articleData.isEditMode) {
        // 编辑模式的HTML
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
        var editIconHtml = allowEditControls
          ? '<img class="img-icon btn-edit-icon" src="/static/project_document/images/preview-review/icon-checklist.png" style="cursor: pointer;" data-id="' + section.id + '" />'
          : '';
        // 预览模式的HTML
        sectionsHtml +=
          '<div class="section-wrapper" data-section-id="' + section.id + '" style="margin-top: ' + sectionMarginTop + ';">' +
          '<div class="section-row">' +
          '<span class="font-section-num text-gradient">' + section.id + '</span>' +
          '<span class="font-section-title">' + section.title + '</span>' +
          editIconHtml +
          '</div>' +
          '<div class="font-content text-content-full" style="display: block; margin-top: 1rem;">' + section.content + '</div>' +
          '</div>';
      }
    }
    return sectionsHtml;
  }

  // 渲染底部操作按钮
  function renderBottomButtons() {
    var container = document.getElementById('edit-action-container');
    if (articleData.isEditMode) {
      container.innerHTML =
        '<div class="btn-cancel-edit" id="btn-cancel-all"><span class="font-btn">取消</span></div>' +
        '<div class="btn-save-edit" id="btn-save-all"><span class="font-btn">保存</span></div>';
      container.style.display = 'flex';
    } else if (allowEditControls) {
      container.innerHTML =
        '<div class="btn-edit-all" id="btn-edit-all"><span class="font-btn">编辑</span></div>';
      container.style.display = 'flex';
    } else {
      container.innerHTML = '';
      container.style.display = 'none';
    }
  }

  function setModeParam(nextMode) {
    if (nextMode) {
      urlParams.set('mode', nextMode);
    } else {
      urlParams.delete('mode');
    }
    var newUrl = window.location.pathname;
    var query = urlParams.toString();
    if (query) {
      newUrl += '?' + query;
    }
    window.history.replaceState({}, '', newUrl);
  }

  function enterEditMode() {
    articleData.isEditMode = true;
    allowEditControls = false;
    setModeParam('edit');
  }

  function exitToEditablePreview() {
    articleData.isEditMode = false;
    allowEditControls = true;
    setModeParam('editable');
  }

  function exitToPreview() {
    articleData.isEditMode = false;
    allowEditControls = false;
    setModeParam(null);
  }

  // ==================== 编辑器逻辑 ====================
  function normalizeText(content) {
    var wrapper = document.createElement('div');
    wrapper.innerHTML = content || '';
    return (wrapper.textContent || wrapper.innerText || '').trim();
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
        lines.push(normalizeText(section.content));
      }
    }
    return lines.join('\n');
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
        alert('链接已复制');
      });
      return;
    }
    var input = document.createElement('input');
    input.value = shareUrl;
    document.body.appendChild(input);
    input.select();
    document.execCommand('copy');
    document.body.removeChild(input);
    alert('链接已复制');
  }

  // 初始化所有编辑器
  function initEditors() {
    if (!window.wangEditor) return;
    var editors = {};

    for (var i = 0; i < articleData.chapters.length; i++) {
      var chapter = articleData.chapters[i];
      for (var j = 0; j < chapter.sections.length; j++) {
        var section = chapter.sections[j];
        var safeId = section.id.replace(/\./g, '_');

        try {
          var editor = window.wangEditor.createEditor({
            selector: '#editor-content-' + safeId,
            html: '<p>' + section.content + '</p>',
            config: { placeholder: '请输入内容' },
            mode: 'default'
          });
          window.wangEditor.createToolbar({
            editor: editor,
            selector: '#writer-toolbar-' + safeId,
            mode: 'default'
          });
          editors[section.id] = editor;
        } catch (e) {
          console.error('编辑器加载失败', e);
        }
      }
    }
    window.allEditors = editors;
  }

  // 打开单个小节编辑器
  function openSingleEditor(sectionId, content) {
    closeSingleEditor();

    var wrapper = document.querySelector('.section-wrapper[data-section-id="' + sectionId + '"]');
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
        html: '<p>' + content + '</p>',
        mode: 'default'
      });
      window.wangEditor.createToolbar({
        editor: currentEditor,
        selector: '#single-toolbar',
        mode: 'default'
      });
      currentEditingSectionId = sectionId;
    }

    editorDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
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

  // ==================== 事件绑定 ====================

  function bindEvents() {
    document.addEventListener('click', function (e) {
      var id = e.target.id;
      var target = e.target;

      if (id === 'btn-share' || target.closest('#btn-share')) {
        sharePage();
        return;
      }

      if (id === 'btn-download' || target.closest('#btn-download')) {
        downloadArticle();
        return;
      }

      if (id === 'btn-polish' || target.closest('#btn-polish')) {
        window.location.href = '../full-compare/index.html';
        return;
      }

      if (id === 'btn-return-writing' || target.closest('#btn-return-writing')) {
        window.location.href = '../writing-workspace/index.html';
        return;
      }

      // 1. 编辑全部
      if (id === 'btn-edit-all' || target.closest('#btn-edit-all')) {
        enterEditMode();
        renderPage();
        return;
      }

      // 2. 取消全部
      if (id === 'btn-cancel-all' || target.closest('#btn-cancel-all')) {
        exitToEditablePreview();
        renderPage();
        return;
      }

      // 3. 保存全部
      if (id === 'btn-save-all' || target.closest('#btn-save-all')) {
        if (window.allEditors) {
          for (var key in window.allEditors) {
            var editor = window.allEditors[key];
            updateSectionContent(key, editor.getText());
          }
        }
        exitToPreview();
        renderPage();
        alert('保存成功');
        return;
      }

      // 4. 点击单个编辑图标
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

      // 5. 单个取消
      if (id === 'btn-cancel-single' || target.closest('#btn-cancel-single')) {
        closeSingleEditor();
        return;
      }

      // 6. 单个保存
      if (id === 'btn-save-single' || target.closest('#btn-save-single')) {
        if (currentEditor) {
          updateSectionContent(currentEditingSectionId, currentEditor.getText());
          closeSingleEditor();
          renderPage();
          alert('保存成功');
        }
        return;
      }

      // 7. 返回首页
      if (target.classList.contains('text-back-home')) {
        window.location.href = '../../index.html';
      }
    });
  }

  // 辅助函数：获取小节内容
  function getSectionContent(sectionId) {
    for (var i = 0; i < articleData.chapters.length; i++) {
      var chapter = articleData.chapters[i];
      for (var j = 0; j < chapter.sections.length; j++) {
        if (chapter.sections[j].id === sectionId) {
          return chapter.sections[j].content;
        }
      }
    }
    return '';
  }

  // 辅助函数：更新小节内容
  function updateSectionContent(sectionId, newContent) {
    for (var i = 0; i < articleData.chapters.length; i++) {
      var chapter = articleData.chapters[i];
      for (var j = 0; j < chapter.sections.length; j++) {
        if (chapter.sections[j].id === sectionId) {
          chapter.sections[j].content = newContent;
          return;
        }
      }
    }
  }

  // ==================== 初始化 ====================
  renderPage();
  bindEvents();
});
